import { createUIMessageStream, createUIMessageStreamResponse, generateText } from 'ai'
import { streamFollowupsToClient } from '../../../utils/devreotesFollowups'
import { db, schema } from '../../../utils/db'
import { and, asc, eq } from 'drizzle-orm'
import { randomUUID } from 'node:crypto'
import { spawn } from 'node:child_process'
import readline from 'node:readline'
import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { z } from 'zod'
import {
  applyDevreotesNdjsonLine,
  consumeDevreotesNdjsonStream,
  type DevreotesFinishBox
} from '../../../utils/devreotesNdjson'
import { buildDevreotesTrace } from '../../../types/devreotes-trace'
import { openai } from '@ai-sdk/openai'

export default defineEventHandler(async (event) => {
  const session = await getUserSession(event)
  const { id } = await getValidatedRouterParams(event, z.object({
    id: z.string()
  }).parse)

  const { message, skipUserInsert } = await readValidatedBody(event, z.object({
    message: z.string().min(1),
    skipUserInsert: z.boolean().optional()
  }).parse)

  const chat = await db.query.chats.findFirst({
    where: () => and(
      eq(schema.chats.id, id as string),
      eq(schema.chats.userId, session.user?.id || session.id)
    ),
    with: {
      messages: {
        orderBy: () => asc(schema.messages.createdAt)
      }
    }
  })
  if (!chat) {
    throw createError({ statusCode: 404, statusMessage: 'Chat not found' })
  }

  if (!skipUserInsert) {
    await db.insert(schema.messages).values({
      chatId: id as string,
      role: 'user',
      parts: [{ type: 'text', text: message }]
    })
  }

  // Build conversational history (summary + last N turns) from stored messages.
  const CONVERSATION_RECENT_TURNS = Number.parseInt(process.env.DEVREOTES_CONVERSATION_RECENT_TURNS || '10', 10) || 10

  const historyMessages = (chat.messages || []).map((m) => {
    let parts: any = m.parts
    if (typeof parts === 'string') {
      try {
        parts = JSON.parse(parts)
      } catch {
        parts = []
      }
    }
    if (!Array.isArray(parts)) {
      parts = []
    }
    const text = parts
      .filter(p => p && typeof p === 'object' && p.type === 'text' && typeof p.text === 'string')
      .map(p => p.text as string)
      .join('\n\n')
      .trim()

    if (!text) {
      return null
    }
    return {
      role: m.role,
      content: text
    }
  }).filter(Boolean) as Array<{ role: string, content: string }>

  const recentHistory = historyMessages.slice(-CONVERSATION_RECENT_TURNS)

  const MAX_SUMMARY_CHARS = Number.parseInt(process.env.DEVREOTES_SUMMARY_MAX_CHARS || '1500', 10) || 1500
  const previousSummary = (chat.summary || '').trim()
  const deterministicFallbackSummary = (() => {
    // Deterministic fallback: keep a rolling window of recent conversation text.
    const summarySource = historyMessages.slice(0, Math.max(0, historyMessages.length - 1))
    const summaryText = summarySource
      .map(m => `${m.role.toUpperCase()}: ${m.content}`)
      .join('\n\n')
    const combined = (previousSummary ? `${previousSummary}\n\n` : '') + summaryText
    return combined.slice(-MAX_SUMMARY_CHARS).trim() || null
  })()
  // Summary we send *with this request* (computed before assistant answer exists).
  const summaryForRequest = deterministicFallbackSummary

  const stream = createUIMessageStream({
    execute: async ({ writer }) => {
      const textId = randomUUID()

      const nuxtRoot = process.cwd()
      const devreotesRoot = process.env.DEVREOTES_ROOT || resolve(nuxtRoot, '..')
      const scriptPath = resolve(nuxtRoot, 'server/python/devreotes_bridge.py')
      const venvPython = resolve(devreotesRoot, '.venv/bin/python')
      const pythonBin
        = process.env.DEVREOTES_PYTHON
          || (existsSync(venvPython) ? venvPython : 'python3')

      writer.write({ type: 'text-start', id: textId })

      const finishBox: DevreotesFinishBox = {
        result: null
      }

      const apiBase = process.env.DEVREOTES_API_URL?.trim()
      if (apiBase) {
        const secret = process.env.DEVREOTES_API_SECRET?.trim()
        const headers: Record<string, string> = {
          'Content-Type': 'application/json'
        }
        if (secret) {
          headers['X-Devreotes-Key'] = secret
        }
        const url = `${apiBase.replace(/\/$/, '')}/chat/stream`
        const res = await fetch(url, {
          method: 'POST',
          headers,
          body: JSON.stringify({
            message,
            summary: summaryForRequest,
            messages: recentHistory
          })
        })
        if (!res.ok) {
          const errText = await res.text().catch(() => '')
          console.error('[devreotes] HTTP API error', {
            url,
            status: res.status,
            body: errText?.slice(0, 500)
          })
          throw new Error(errText || `Devreotes API HTTP ${res.status}`)
        }
        if (!res.body) {
          throw new Error('Empty response body from Devreotes API')
        }
        await consumeDevreotesNdjsonStream(res.body, writer, textId, finishBox)
      } else {
        let stderr = ''
        const proc = spawn(pythonBin, [scriptPath], {
          cwd: devreotesRoot,
          env: {
            ...process.env,
            DEVREOTES_ROOT: devreotesRoot,
            DEVREOTES_STREAM: '1',
            PYTHONUNBUFFERED: '1',
            CUDA_VISIBLE_DEVICES: process.env.CUDA_VISIBLE_DEVICES ?? ''
          }
        })

        proc.stderr?.on('data', (chunk: Buffer) => {
          stderr += chunk.toString()
        })

        await new Promise<void>((resolvePromise, rejectPromise) => {
          const rl = readline.createInterface({ input: proc.stdout, crlfDelay: Infinity })

          rl.on('line', (line) => {
            const trimmed = line.trim()
            applyDevreotesNdjsonLine(trimmed, writer, textId, finishBox)
          })

          proc.on('error', rejectPromise)
          proc.on('close', (code) => {
            rl.close()
            if (code !== 0) {
              const detail = finishBox.bridgeError || stderr || '(no message)'
              console.error('[devreotes] Python bridge failed', {
                code,
                pythonBin,
                scriptPath,
                devreotesRoot,
                stderr: stderr || '(empty)',
                stdoutError: finishBox.bridgeError ?? '(none parsed)'
              })
              rejectPromise(
                new Error(
                  finishBox.bridgeError
                    || stderr
                    || `Bridge exited with code ${code}`
                )
              )
            } else {
              resolvePromise()
            }
          })

          const bridgePayload = JSON.stringify({
            message,
            summary: summaryForRequest,
            messages: recentHistory
          })
          proc.stdin.write(bridgePayload)
          proc.stdin.end()
        })
      }

      writer.write({ type: 'text-end', id: textId })

      const finishResult = finishBox.result
      if (!finishResult) {
        throw createError({ statusCode: 500, statusMessage: 'No finish payload from Devreotes backend' })
      }
      if (finishResult.error) {
        throw createError({ statusCode: 500, statusMessage: String(finishResult.error) })
      }

      const answer = (finishResult.answer || '').trim() || 'No response produced by backend.'
      const traceBackend = apiBase ? 'http' : 'bridge'

      const recentUserQuestions = [
        ...historyMessages.filter(m => m.role === 'user').map(m => m.content.trim()),
        message.trim()
      ].filter(Boolean)

      const suggestedFollowups = await streamFollowupsToClient(writer, {
        userQuestion: message,
        answer,
        finishResult,
        recentUserQuestions
      })

      writer.write({ type: 'finish' })

      await db.insert(schema.messages).values({
        chatId: id as string,
        role: 'assistant',
        parts: [{ type: 'text', text: answer }],
        devreotesTrace: buildDevreotesTrace(
          finishResult,
          traceBackend,
          suggestedFollowups.length ? suggestedFollowups : undefined
        )
      })

      // LLM-based rolling summary update (per thread).
      // Goal: a compact state representation for follow-up resolution, not corpus evidence.
      let nextSummary: string | null = deterministicFallbackSummary
      try {
        const modelName = process.env.DEVREOTES_SUMMARY_MODEL || 'openai/gpt-4o-mini'
        const modelId = (() => {
          const m = (modelName || '').trim()
          if (!m) return 'gpt-4o-mini'
          if (m.includes('/')) return m.split('/').pop() || 'gpt-4o-mini'
          return m
        })()
        const model = openai(modelId)
        const transcript = [...recentHistory, { role: 'assistant', content: answer }]
          .map(m => `${m.role.toUpperCase()}: ${m.content}`)
          .join('\n\n')

        const { text } = await generateText({
          model,
          system:
            'You update a short conversation summary for a research-chat thread. ' +
            'This summary is ONLY for reference resolution in future turns, not for answering from corpus evidence. ' +
            'Do not add citations, do not invent facts, and do not introduce new scientific claims. ' +
            'Keep it concise, focusing on: user intent, key entities mentioned (genes/authors/papers), and any constraints (corpus-only).',
          prompt:
            `Previous summary (may be empty):\n${previousSummary || '(empty)'}\n\n` +
            `Recent turns:\n${transcript}\n\n` +
            `Write an updated summary in plain text (no headings, no markdown), ` +
            `max ${MAX_SUMMARY_CHARS} characters.`,
          maxTokens: 400
        })
        const cleaned = (text || '').trim()
        if (cleaned) {
          nextSummary = cleaned.slice(0, MAX_SUMMARY_CHARS).trim() || nextSummary
        }
      } catch {
        // Keep deterministic fallback.
      }

      // Persist updated summary for this thread.
      if (nextSummary !== null) {
        await db.update(schema.chats)
          .set({ summary: nextSummary })
          .where(eq(schema.chats.id, id as string))
      }

      if (!chat.title) {
        await db.update(schema.chats)
          .set({ title: message.slice(0, 30) })
          .where(eq(schema.chats.id, id as string))
      }
    }
  })

  return createUIMessageStreamResponse({ stream })
})
