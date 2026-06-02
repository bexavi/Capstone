/** Mirrors server NDJSON progress lines (client-safe, no server import). */
export type DevreotesProgressNdjson =
  | { type: 'agent_status', phase?: string, message: string }
  | {
      type: 'agent_plan'
      plan: {
        summary?: string
        steps?: Array<{ id: string, label: string, status: string }>
        tool_sequence?: string[]
      }
    }
  | { type: 'agent_step', step_id?: string, status?: string, label?: string }

export type DevreotesAgentPlanPayload = NonNullable<
  Extract<DevreotesProgressNdjson, { type: 'agent_plan' }>['plan']
>

/** Client-side snapshot merged from streamed progress events. */
export type DevreotesStreamProgress = {
  message: string
  phase?: string
  plan: DevreotesAgentPlanPayload | null
  toolSteps: Array<{ step_id: string, label: string, status: string }>
}

export function emptyDevreotesStreamProgress(): DevreotesStreamProgress {
  return { message: '', phase: undefined, plan: null, toolSteps: [] }
}

export function mergeDevreotesProgress(
  prev: DevreotesStreamProgress,
  raw: DevreotesProgressNdjson
): DevreotesStreamProgress {
  if (raw.type === 'agent_status') {
    return { ...prev, message: raw.message, phase: raw.phase }
  }
  if (raw.type === 'agent_plan') {
    return { ...prev, plan: raw.plan }
  }
  if (raw.type === 'agent_step') {
    const id = raw.step_id || 'unknown'
    const next = [...prev.toolSteps]
    const idx = next.findIndex(s => s.step_id === id)
    const row = {
      step_id: id,
      label: (raw.label || id).trim(),
      status: (raw.status || 'active').trim()
    }
    if (idx >= 0) {
      next[idx] = row
    } else {
      next.push(row)
    }
    return { ...prev, toolSteps: next }
  }
  return prev
}

export function devreotesProgressIsEmpty(p: DevreotesStreamProgress): boolean {
  return (
    !p.message.trim()
    && !p.plan
    && p.toolSteps.length === 0
  )
}
