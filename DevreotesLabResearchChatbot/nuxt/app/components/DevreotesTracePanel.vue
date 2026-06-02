<script setup lang="ts">
import type { DevreotesTrace } from '~/types/devreotes-trace'

const { trace } = defineProps<{
  trace: DevreotesTrace
}>()

/** Start expanded so users see audit info without hunting for a control. */
const open = ref(false)

const previewJson = computed(() => {
  const prev = trace.retrieval_preview
  if (prev == null || (Array.isArray(prev) && prev.length === 0)) {
    return ''
  }
  try {
    return JSON.stringify(prev, null, 2)
  } catch {
    return String(prev)
  }
})

const toolsJson = computed(() => {
  const t = trace.tool_calls_log
  if (!t?.length) {
    return ''
  }
  try {
    return JSON.stringify(t, null, 2)
  } catch {
    return ''
  }
})

const planJson = computed(() => {
  const p = trace.agent_plan
  if (!p) {
    return ''
  }
  try {
    return JSON.stringify(p, null, 2)
  } catch {
    return ''
  }
})

const reasoningJson = computed(() => {
  const r = trace.reasoning_log
  if (!r?.length) {
    return ''
  }
  try {
    return JSON.stringify(r, null, 2)
  } catch {
    return String(r)
  }
})
</script>

<template>
  <UCollapsible v-model:open="open" class="flex flex-col gap-1 mt-3 border border-default rounded-lg p-2 bg-elevated/30">
    <UButton
      class="p-0 group justify-start"
      color="neutral"
      variant="ghost"
      size="sm"
      trailing-icon="i-lucide-chevron-down"
      :ui="{
        trailingIcon: 'group-data-[state=open]:rotate-180 transition-transform duration-200'
      }"
      label="Retrieval trace"
    />

    <template #content>
      <dl class="grid gap-2 text-xs sm:text-sm text-muted font-mono">
        <div v-if="trace.query_type_label || trace.query_type" class="grid gap-0.5">
          <dt class="text-[var(--ui-text-muted)] font-sans uppercase tracking-wide text-[10px]">
            Route
          </dt>
          <dd class="text-default font-sans">
            {{ trace.query_type_label || trace.query_type || '—' }}
            <span v-if="trace.routed_key != null && trace.routed_key !== ''" class="text-muted">
              ({{ trace.routed_key }})
            </span>
          </dd>
        </div>
        <div class="grid gap-0.5">
          <dt class="text-[var(--ui-text-muted)] font-sans uppercase tracking-wide text-[10px]">
            Backend
          </dt>
          <dd>{{ trace.backend }}</dd>
        </div>
        <div v-if="trace.results_count != null" class="grid gap-0.5">
          <dt class="text-[var(--ui-text-muted)] font-sans uppercase tracking-wide text-[10px]">
            Results
          </dt>
          <dd>{{ trace.results_count }}</dd>
        </div>
        <div v-if="trace.clarification_required" class="grid gap-0.5">
          <dt class="text-[var(--ui-text-muted)] font-sans uppercase tracking-wide text-[10px]">
            Clarification
          </dt>
          <dd class="font-sans text-default">
            Planner asked for user input before retrieval (no tools run).
          </dd>
        </div>
        <div v-if="planJson" class="grid gap-0.5">
          <dt class="text-[var(--ui-text-muted)] font-sans uppercase tracking-wide text-[10px]">
            Agent plan
          </dt>
          <dd>
            <pre class="max-h-40 overflow-auto rounded bg-muted/50 p-2 text-[11px] leading-snug whitespace-pre-wrap">{{ planJson }}</pre>
          </dd>
        </div>
        <div v-if="reasoningJson" class="grid gap-0.5">
          <dt class="text-[var(--ui-text-muted)] font-sans uppercase tracking-wide text-[10px]">
            Reasoning log
          </dt>
          <dd class="font-sans text-[10px] text-muted leading-snug mb-1">
            Optional model notes (enable only if you accept privacy tradeoffs).
          </dd>
          <dd>
            <pre class="max-h-48 overflow-auto rounded bg-muted/50 p-2 text-[11px] leading-snug whitespace-pre-wrap">{{ reasoningJson }}</pre>
          </dd>
        </div>
        <div v-if="trace.abstained" class="grid gap-0.5">
          <dt class="text-[var(--ui-text-muted)] font-sans uppercase tracking-wide text-[10px]">
            Abstain
          </dt>
          <dd>{{ trace.abstain_reason || 'yes' }}</dd>
        </div>
        <div v-if="trace.sources?.length" class="grid gap-0.5">
          <dt class="text-[var(--ui-text-muted)] font-sans uppercase tracking-wide text-[10px]">
            Sources
          </dt>
          <dd>
            <ul class="list-disc pl-4 font-sans text-default max-h-32 overflow-y-auto">
              <li v-for="(s, i) in trace.sources.slice(0, 12)" :key="i">
                {{ s }}
              </li>
            </ul>
          </dd>
        </div>
        <div v-if="toolsJson" class="grid gap-0.5">
          <dt class="text-[var(--ui-text-muted)] font-sans uppercase tracking-wide text-[10px]">
            Tool calls
          </dt>
          <dd>
            <pre class="max-h-40 overflow-auto rounded bg-muted/50 p-2 text-[11px] leading-snug whitespace-pre-wrap">{{ toolsJson }}</pre>
          </dd>
        </div>
        <div v-if="previewJson" class="grid gap-0.5">
          <dt class="text-[var(--ui-text-muted)] font-sans uppercase tracking-wide text-[10px]">
            Retrieval preview
          </dt>
          <dd>
            <pre class="max-h-56 overflow-auto rounded bg-muted/50 p-2 text-[11px] leading-snug whitespace-pre-wrap">{{ previewJson }}</pre>
          </dd>
        </div>
      </dl>
    </template>
  </UCollapsible>
</template>
