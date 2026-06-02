import type { UIMessage } from 'ai'
import { db, schema } from '../utils/db'
import { and, eq } from 'drizzle-orm'
import { z } from 'zod'

export default defineEventHandler(async (event) => {
  const session = await getUserSession(event)
  const userId = session.user?.id || session.id
  const { id, message } = await readValidatedBody(event, z.object({
    id: z.string(),
    message: z.custom<UIMessage>()
  }).parse)

  const isDuplicateChatIdError = (err: unknown): boolean => {
    const e = err as { code?: string, constraint?: string, cause?: { code?: string, constraint?: string } }
    return e?.code === '23505'
      || e?.constraint === 'chats_pkey'
      || e?.cause?.code === '23505'
      || e?.cause?.constraint === 'chats_pkey'
  }

  let chat = null as null | { id: string, title: string | null, userId: string }

  try {
    const [created] = await db.insert(schema.chats).values({
      id,
      title: '',
      userId
    }).returning()
    chat = created ?? null
  } catch (err) {
    if (!isDuplicateChatIdError(err)) {
      throw err
    }
    // Idempotent retry path: reuse existing chat for this user.
    chat = await db.query.chats.findFirst({
      where: () => and(
        eq(schema.chats.id, id as string),
        eq(schema.chats.userId, userId)
      )
    }) as typeof chat
  }

  if (!chat) {
    throw createError({ statusCode: 500, statusMessage: 'Failed to create or load chat' })
  }

  const existingMessage = await db.query.messages.findFirst({
    where: () => eq(schema.messages.chatId, chat.id)
  })
  if (!existingMessage) {
    await db.insert(schema.messages).values({
      chatId: chat.id,
      role: 'user',
      parts: message.parts
    })
  }

  return chat
})
