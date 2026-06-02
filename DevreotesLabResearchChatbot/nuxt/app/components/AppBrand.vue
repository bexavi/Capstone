<script setup lang="ts">
withDefaults(
  defineProps<{
    collapsed?: boolean
  }>(),
  { collapsed: false }
)
</script>

<template>
  <NuxtLink
    to="/"
    class="flex items-center gap-2.5 min-w-0 rounded-md outline-none ring-offset-2 focus-visible:ring-2 focus-visible:ring-primary"
  >
    <div
      class="size-9 shrink-0 rounded-lg flex items-center justify-center text-lg leading-none select-none
        bg-gradient-to-br from-sky-500 to-cyan-500 text-white
        shadow-[0_0_0_1px_rgba(14,165,233,0.3),0_4px_12px_rgba(14,165,233,0.2)]"
      aria-hidden="true"
    >
      🧬
    </div>
    <div v-if="!collapsed" class="min-w-0 flex flex-col text-start">
      <span
        class="text-[17px] leading-tight tracking-tight text-highlighted font-devreotes-display"
      >
        Devreotes Lab
      </span>
      <span class="text-[11px] uppercase tracking-[0.04em] text-muted mt-px">
        Research Intelligence
      </span>
    </div>
  </NuxtLink>
</template>
