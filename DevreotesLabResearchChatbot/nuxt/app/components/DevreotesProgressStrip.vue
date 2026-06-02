<script setup lang="ts">
import type { DevreotesStreamProgress } from '~/utils/devreotesProgress'

const { progress } = defineProps<{
  progress: DevreotesStreamProgress
}>()

const planOpen = ref(false)

const toolLines = computed(() => {
  const t = progress.toolSteps
  if (!t.length) {
    return []
  }
  return [...t].slice(-12)
})

const planSteps = computed(() => progress.plan?.steps?.filter(s => s.label?.trim()) ?? [])
</script>

<template>
  <div
    v-if="progress.message.trim() || progress.plan || toolLines.length"
    class="w-full min-w-0 max-w-full overflow-hidden rounded-lg border border-default bg-elevated/40 px-3 py-2 text-sm text-muted mb-2"
  >
    <div v-if="progress.message.trim()" class="flex min-w-0 items-start gap-2 text-default">
      <span class="i-lucide-loader-circle shrink-0 mt-0.5 size-4 animate-spin text-primary" aria-hidden="true" />
      <span class="min-w-0 flex-1 break-words leading-snug [overflow-wrap:anywhere]">{{ progress.message }}</span>
    </div>
    <div v-else-if="toolLines.length" class="flex min-w-0 items-center gap-2 text-default text-xs">
      <span class="i-lucide-loader-circle size-3.5 shrink-0 animate-spin text-primary" aria-hidden="true" />
      <span class="min-w-0 break-words">Running retrieval tools…</span>
    </div>

    <UCollapsible
      v-if="planSteps.length || (progress.plan?.summary && progress.plan.summary.trim())"
      v-model:open="planOpen"
      class="mt-2 min-w-0 max-w-full"
    >
      <UButton
        class="group h-auto min-h-0 w-full min-w-0 max-w-full justify-start gap-2 whitespace-normal p-0 py-1 text-left"
        color="neutral"
        variant="ghost"
        size="xs"
        trailing-icon="i-lucide-chevron-down"
        :ui="{
          base: 'w-full min-w-0 max-w-full flex items-start',
          trailingIcon: 'mt-0.5 shrink-0 group-data-[state=open]:rotate-180 transition-transform duration-200'
        }"
      >
        <span class="min-w-0 flex-1 text-wrap break-words text-xs font-normal leading-snug [overflow-wrap:anywhere]">
          {{ progress.plan?.summary?.trim() || 'Planned steps' }}
        </span>
      </UButton>
      <template #content>
        <ol v-if="planSteps.length" class="mt-1 min-w-0 list-decimal pl-4 text-xs text-muted space-y-0.5">
          <li v-for="s in planSteps" :key="s.id" class="break-words leading-snug [overflow-wrap:anywhere]">
            {{ s.label }}
          </li>
        </ol>
      </template>
    </UCollapsible>

    <ul v-if="toolLines.length" class="mt-2 min-w-0 space-y-0.5 border-t border-default/60 pt-2 font-mono text-xs text-muted">
      <li v-for="(row, i) in toolLines" :key="`${row.step_id}-${i}`" class="flex min-w-0 gap-2">
        <span class="w-14 shrink-0 text-[10px] uppercase">{{ row.status }}</span>
        <span class="min-w-0 flex-1 break-words text-default/90 [overflow-wrap:anywhere]">{{ row.label }}</span>
      </li>
    </ul>
  </div>
</template>
