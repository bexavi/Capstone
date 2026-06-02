import { streamText } from 'ai'
import type { UIMessage, UIMessageStreamWriter } from 'ai'
import type { DevreotesResult } from './devreotesNdjson'
import { openai } from '@ai-sdk/openai'

function normalizeOpenAIModelId(modelName: string): string {
  const m = (modelName || '').trim()
  if (!m) return 'gpt-4o-mini'
  // Accept values like `openai/gpt-4o-mini` or `gpt-4o-mini`.
  if (m.includes('/')) return m.split('/').pop() || 'gpt-4o-mini'
  return m
}

export type FollowupsStreamData =
  | { partial: string, suggestions?: undefined, done?: false }
  | { partial: string, suggestions: string[], done: true }

function writeFollowupsData(
  writer: UIMessageStreamWriter<UIMessage>,
  data: FollowupsStreamData
): void {
  writer.write({
    type: 'data-devreotes-followups',
    data
  } as Parameters<UIMessageStreamWriter<UIMessage>['write']>[0])
}

function followupsEnabled(): boolean {
  const v = process.env.DEVREOTES_FOLLOWUPS_ENABLED ?? '1'
  return v === '1' || v.toLowerCase() === 'true' || v.toLowerCase() === 'yes'
}

function followupsCount(): number {
  const n = Number.parseInt(process.env.DEVREOTES_FOLLOWUPS_COUNT || '4', 10)
  return Number.isFinite(n) && n > 0 ? Math.min(n, 8) : 4
}

function maxPreviewChars(): number {
  const n = Number.parseInt(process.env.DEVREOTES_FOLLOWUPS_MAX_PREVIEW_CHARS || '4000', 10)
  return Number.isFinite(n) && n > 0 ? n : 4000
}

function parseSuggestionsJson(raw: string): string[] {
  const trimmed = (raw ?? '').trim()
  if (!trimmed) return []

  // If the model returned a fenced code block, prefer the inside content.
  const fence = /^```(?:json)?\s*([\s\S]*?)```$/m.exec(trimmed)
  if (fence?.[1]) {
    return parseSuggestionsJson(fence[1].trim())
  }

  // Fast path: exact JSON array.
  try {
    const parsed = JSON.parse(trimmed) as unknown
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter((x): x is string => typeof x === 'string')
      .map(s => s.trim())
      .filter(s => s.length > 0)
  } catch {
    // fall through to "extract first array" strategy
  }

  // Robust path: extract the first JSON array substring from any extra surrounding text.
  // Example failure mode: "Sure! [\"Q1\",\"Q2\"]"
  try {
    const match = trimmed.match(/\[[\s\S]*\]/)
    if (!match) return []
    const parsed = JSON.parse(match[0]) as unknown
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter((x): x is string => typeof x === 'string')
      .map(s => s.trim())
      .filter(s => s.length > 0)
  } catch {
    return []
  }
}

/**
 * Streams LLM output as JSON array of follow-up questions, forwarding partial text via UI data chunks.
 * Returns parsed suggestions (may be empty on failure).
 */
export async function streamFollowupsToClient(
  writer: UIMessageStreamWriter<UIMessage>,
  params: {
    userQuestion: string
    answer: string
    finishResult: DevreotesResult
    recentUserQuestions: string[]
  }
): Promise<string[]> {
  if (!followupsEnabled()) {
    return []
  }

  const count = followupsCount()
  const modelName = process.env.DEVREOTES_FOLLOWUPS_MODEL?.trim()
    || process.env.DEVREOTES_SUMMARY_MODEL?.trim()
    || 'openai/gpt-4o-mini'
  const model = openai(normalizeOpenAIModelId(modelName))

  const { userQuestion, answer, finishResult, recentUserQuestions } = params
  let preview = ''
  try {
    preview = JSON.stringify(finishResult.retrieval_preview ?? null)
  } catch {
    preview = ''
  }
  if (preview.length > maxPreviewChars()) {
    preview = `${preview.slice(0, maxPreviewChars())}…`
  }

  const avoid = recentUserQuestions
    .map(q => q.trim())
    .filter(Boolean)
    .slice(-12)
    .join('\n- ')

  const system =
    'You suggest short follow-up questions for a research literature chatbot (Prof. Devreotes lab papers). '
    + 'Output ONLY a JSON array of strings, no markdown, no keys, no commentary. '
    + `Exactly ${count} distinct questions. Each question must be one line, under 180 characters. `
    + 'Questions should be answerable from the same paper corpus (chemotaxis, signaling, genes, methods). '
    + 'Do not invent facts. Do not repeat or paraphrase the user questions listed under "Avoid repeating".'

  const prompt =
    `User question:\n${userQuestion}\n\n`
    + `Assistant answer (for context only):\n${answer.slice(0, 12000)}\n\n`
    + `Retrieval context (titles/snippets, may be truncated):\n${preview || '(none)'}\n\n`
    + `Citation source ids if any: ${(finishResult.sources || []).join(', ') || '(none)'}\n`
    + `Query route: ${finishResult.query_type_label || finishResult.query_type || 'unknown'}\n`
    + `Abstained: ${Boolean(finishResult.abstained)}\n\n`
    + `Avoid repeating these user questions:\n${avoid ? `- ${avoid}` : '(none)'}\n\n`
    + `Return a JSON array of ${count} strings.`

  let accumulated = ''
  try {
    const result = streamText({
      model,
      system,
      prompt,
      maxOutputTokens: 512
    })

    for await (const delta of result.textStream) {
      accumulated += delta
      writeFollowupsData(writer, { partial: accumulated })
    }
  } catch {
    writeFollowupsData(writer, { partial: accumulated, suggestions: [], done: true })
    return []
  }

  let suggestions: string[] = []
  try {
    suggestions = parseSuggestionsJson(accumulated).slice(0, count)
  } catch {
    suggestions = []
  }

  writeFollowupsData(writer, { partial: accumulated, suggestions, done: true })

  return suggestions
}
