/** Client-safe mirror of server DevreotesTrace (audit / retrieval snapshot). */
export type DevreotesThemesMeta = {
  themes_limit?: number
  truncated?: boolean
  metric?: string
  sort?: string
}

export type DevreotesAgentPlan = {
  subtasks?: string[]
  tool_sequence?: string[]
  missing_parameters?: string[]
  needs_user_input?: boolean
  clarification_prompt?: string
  notes?: string
}

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
  suggested_followups?: string[]
}
