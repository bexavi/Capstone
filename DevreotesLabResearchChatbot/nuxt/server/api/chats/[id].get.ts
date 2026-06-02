import { db, schema } from '../../utils/db'
import { and, asc, eq } from 'drizzle-orm'
import { z } from 'zod'

function normalizeDbMessage(msg: {
  parts?: unknown
  devreotesTrace?: unknown
  devreotes_trace?: unknown
  [key: string]: unknown
}) {
  let parts = msg.parts
  if (typeof parts === 'string') {
    try {
      parts = JSON.parse(parts) as unknown
    } catch {
      parts = []
    }
  }
  if (!Array.isArray(parts)) {
    parts = []
  }
  let trace = msg.devreotesTrace ?? msg.devreotes_trace
  if (typeof trace === 'string') {
    try {
      trace = JSON.parse(trace) as unknown
    } catch {
      trace = null
    }
  }
  return { ...msg, parts, devreotesTrace: trace, devreotes_trace: trace }
}

export default defineEventHandler(async (event) => {
  const session = await getUserSession(event)

  const { id } = await getValidatedRouterParams(event, z.object({
    id: z.string()
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

  const messages = (chat.messages || []).map(m => normalizeDbMessage(m as Record<string, unknown>))
  return { ...chat, messages }
})
