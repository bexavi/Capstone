import type { DevreotesAgentPlan, DevreotesResult, DevreotesThemesMeta } from '../utils/devreotesNdjson'

/** Persisted audit snapshot (no duplicate answer text). */
export type DevreotesTrace = {
  trace_version: 1
  backend: 'http' | 'bridge'
  query_type?: string
  query_type_label?: string
  routed_key?: string | null
  results_count?: number
  sources?: string[]
  retrieval_preview?: unknown[]
  abstained?: boolean
  abstain_reason?: string | null
  tool_calls_log?: Array<{ name?: string; args?: Record<string, unknown> }>
  themes_meta?: DevreotesThemesMeta
  clarification_required?: boolean
  agent_plan?: DevreotesAgentPlan
  reasoning_log?: Array<{ kind?: string, step?: number, text?: string }>
  /** Dynamic follow-up questions (also streamed over SSE before persist). */
  suggested_followups?: string[]
}

export function buildDevreotesTrace(
  result: DevreotesResult,
  backend: 'http' | 'bridge',
  suggested_followups?: string[]
): DevreotesTrace {
  return {
    trace_version: 1,
    backend,
    query_type: result.query_type,
    query_type_label: result.query_type_label,
    routed_key: result.routed_key ?? null,
    results_count: result.results_count,
    sources: result.sources,
    retrieval_preview: result.retrieval_preview,
    abstained: result.abstained,
    abstain_reason: result.abstain_reason ?? null,
    tool_calls_log: result.tool_calls_log,
    themes_meta: result.themes_meta,
    ...(result.clarification_required ? { clarification_required: true } : {}),
    ...(result.agent_plan ? { agent_plan: result.agent_plan } : {}),
    ...(result.reasoning_log?.length ? { reasoning_log: result.reasoning_log } : {}),
    ...(suggested_followups?.length ? { suggested_followups } : {})
  }
}
