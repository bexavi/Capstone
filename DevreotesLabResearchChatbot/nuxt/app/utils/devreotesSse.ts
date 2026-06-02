import type { DevreotesProgressNdjson } from './devreotesProgress'

export type DevreotesFollowupsStreamEvent =
  | { kind: 'partial', partial: string }
  | { kind: 'done', partial: string, suggestions: string[] }

function parseSseDataLine(
  line: string,
  onDelta: (delta: string) => void,
  onFollowups?: (ev: DevreotesFollowupsStreamEvent) => void,
  onProgress?: (ev: DevreotesProgressNdjson) => void
): void {
  if (!line.startsWith('data:')) {
    return
  }
  const payload = line.replace(/^data:\s?/, '').trim()
  if (payload === '[DONE]') {
    return
  }
  try {
    const chunk = JSON.parse(payload) as {
      type?: string
      delta?: string
      errorText?: string
      data?: unknown
    }
    if (chunk.type === 'error' && chunk.errorText) {
      throw new Error(chunk.errorText)
    }
    if (chunk.type === 'text-delta' && typeof chunk.delta === 'string') {
      onDelta(chunk.delta)
    }
    if (chunk.type === 'data-devreotes-progress' && chunk.data && typeof chunk.data === 'object') {
      const d = chunk.data as { type?: string }
      if (d.type === 'agent_status' || d.type === 'agent_plan' || d.type === 'agent_step') {
        onProgress?.(chunk.data as DevreotesProgressNdjson)
      }
    }
    if (chunk.type === 'data-devreotes-followups' && chunk.data && typeof chunk.data === 'object') {
      const d = chunk.data as { partial?: string, suggestions?: string[], done?: boolean }
      if (d.done === true) {
        onFollowups?.({
          kind: 'done',
          partial: typeof d.partial === 'string' ? d.partial : '',
          suggestions: Array.isArray(d.suggestions) ? d.suggestions : []
        })
      } else if (typeof d.partial === 'string') {
        onFollowups?.({ kind: 'partial', partial: d.partial })
      }
    }
  } catch (e) {
    if (e instanceof SyntaxError) {
      return
    }
    throw e
  }
}

/**
 * Consumes the Server-Sent Events body from createUIMessageStreamResponse (AI SDK).
 * Avoids DefaultChatTransport + readUIMessageStream, which can fail silently in the browser
 * when chunk parsing or message-id handling does not match the stream.
 */
export async function consumeDevreotesUiSse(
  body: ReadableStream<Uint8Array>,
  onDelta: (delta: string) => void,
  options?: {
    onFollowups?: (ev: DevreotesFollowupsStreamEvent) => void
    onProgress?: (ev: DevreotesProgressNdjson) => void
  }
): Promise<void> {
  const onFollowups = options?.onFollowups
  const onProgress = options?.onProgress
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buf = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }
    buf += decoder.decode(value, { stream: true })

    let sep: number
    while ((sep = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, sep)
      buf = buf.slice(sep + 2)

      for (const line of block.split('\n')) {
        parseSseDataLine(line, onDelta, onFollowups, onProgress)
      }
    }
  }

  for (const line of buf.split('\n')) {
    parseSseDataLine(line, onDelta, onFollowups, onProgress)
  }
}
