import type { UIMessage, UIMessageStreamWriter } from 'ai'

export type DevreotesFinishBox = {
  result: DevreotesResult | null
  bridgeError?: string
}

/** Backend metadata for corpus gene-frequency (themes) retrieval — ranked, capped, not full :Gene census. */
export type DevreotesThemesMeta = {
  themes_limit?: number
  truncated?: boolean
  metric?: string
  sort?: string
}

/** One progress event streamed to the UI (mirrors Python NDJSON types). */
export type DevreotesProgressNdjson =
  | { type: 'agent_status', phase?: string, message: string }
  | { type: 'agent_plan', plan: DevreotesAgentPlanPayload }
  | { type: 'agent_step', step_id?: string, status?: string, label?: string }

export type DevreotesAgentPlanPayload = {
  summary?: string
  steps?: Array<{ id: string, label: string, status: string }>
  tool_sequence?: string[]
}

/** Structured plan from explicit agent planner (when enabled). */
export type DevreotesAgentPlan = {
  subtasks?: string[]
  tool_sequence?: string[]
  missing_parameters?: string[]
  needs_user_input?: boolean
  clarification_prompt?: string
  notes?: string
}

export type DevreotesResult = {
  answer?: string
  query_type?: string
  query_type_label?: string
  routed_key?: string | null
  results_count?: number
  sources?: string[]
  retrieval_preview?: unknown[]
  abstained?: boolean
  abstain_reason?: string | null
  error?: string
  tool_calls_log?: Array<{ name?: string; args?: Record<string, unknown> }>
  themes_meta?: DevreotesThemesMeta
  /** Planner asked for user input before running retrieval tools. */
  clarification_required?: boolean
  agent_plan?: DevreotesAgentPlan
  /** Model chain-of-thought snippets when DEVREOTES_AGENT_REASONING_LOG=true (sensitive). */
  reasoning_log?: Array<{ kind?: string, step?: number, text?: string }>
}

/**
 * One NDJSON line from devreotes_bridge.py or FastAPI /chat/stream (stdout / HTTP body).
 */
export function applyDevreotesNdjsonLine(
  trimmed: string,
  writer: UIMessageStreamWriter,
  textId: string,
  finishBox: DevreotesFinishBox
): void {
  if (!trimmed.startsWith('{')) {
    return
  }
  try {
    const obj = JSON.parse(trimmed) as {
      type?: string
      text?: string
      result?: DevreotesResult
      error?: string
    }
    if (typeof obj.error === 'string' && obj.type == null) {
      finishBox.bridgeError = obj.error
      return
    }
    if (obj.type === 'delta' && typeof obj.text === 'string') {
      writer.write({ type: 'text-delta', id: textId, delta: obj.text })
    } else if (obj.type === 'finish' && obj.result) {
      finishBox.result = obj.result
    } else if (
      obj.type === 'agent_status'
      && typeof (obj as { message?: string }).message === 'string'
    ) {
      writer.write({
        type: 'data-devreotes-progress',
        data: obj as DevreotesProgressNdjson
      } as Parameters<UIMessageStreamWriter<UIMessage>['write']>[0])
    } else if (obj.type === 'agent_plan' && (obj as { plan?: unknown }).plan) {
      writer.write({
        type: 'data-devreotes-progress',
        data: obj as DevreotesProgressNdjson
      } as Parameters<UIMessageStreamWriter<UIMessage>['write']>[0])
    } else if (obj.type === 'agent_step') {
      writer.write({
        type: 'data-devreotes-progress',
        data: obj as DevreotesProgressNdjson
      } as Parameters<UIMessageStreamWriter<UIMessage>['write']>[0])
    }
  } catch {
    /* ignore malformed lines */
  }
}

/**
 * Consume a byte stream of NDJSON lines (HTTP response body from FastAPI).
 */
export async function consumeDevreotesNdjsonStream(
  body: ReadableStream<Uint8Array>,
  writer: UIMessageStreamWriter,
  textId: string,
  finishBox: DevreotesFinishBox
): Promise<void> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buf = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }
    buf += decoder.decode(value, { stream: true })

    let nl: number
    while ((nl = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, nl).trim()
      buf = buf.slice(nl + 1)
      applyDevreotesNdjsonLine(line, writer, textId, finishBox)
    }
  }

  const tail = buf.trim()
  if (tail.length > 0) {
    applyDevreotesNdjsonLine(tail, writer, textId, finishBox)
  }
}
