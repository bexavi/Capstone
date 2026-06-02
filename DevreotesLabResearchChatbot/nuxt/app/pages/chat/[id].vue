<script setup lang="ts">
import type { DefineComponent } from 'vue'
import type { UIMessage } from 'ai'
import { useClipboard } from '@vueuse/core'
import { getTextFromMessage } from '@nuxt/ui/utils/ai'
import { consumeDevreotesUiSse } from '../../utils/devreotesSse'
import ProseStreamPre from '../../components/prose/PreStream.vue'
import DevreotesTracePanel from '../../components/DevreotesTracePanel.vue'
import DevreotesProgressStrip from '../../components/DevreotesProgressStrip.vue'
import type { DevreotesTrace } from '~/types/devreotes-trace'
import {
  devreotesProgressIsEmpty,
  emptyDevreotesStreamProgress,
  mergeDevreotesProgress,
  type DevreotesStreamProgress
} from '~/utils/devreotesProgress'
import { injectCitationMarkdown } from '~/utils/injectCitationMarkdown'
import { normalizeAssistantMathMarkdown } from '~/utils/normalizeAssistantMathMarkdown'

/** UIMessage plus optional persisted Devreotes audit row from Hub DB. */
type ChatMessage = UIMessage & { devreotesTrace?: DevreotesTrace | null }

/** API / DB may expose camelCase or snake_case for the JSON column. */
function traceFromRow(msg: ChatMessage | Record<string, unknown>): DevreotesTrace | undefined {
  const m = msg as ChatMessage & { devreotes_trace?: DevreotesTrace }
  return m.devreotesTrace ?? m.devreotes_trace
}

/**
 * Resolve trace for UI: slot `message` may omit extra fields — fall back to `messages` ref by id.
 */
function devreotesTraceForMessage(msg: ChatMessage): DevreotesTrace | undefined {
  const direct = traceFromRow(msg)
  if (direct) {
    return direct
  }
  const full = messages.value.find(x => x.id === msg.id)
  return full ? traceFromRow(full) : undefined
}

function assistantMarkdownWithCitations(text: string, msg: ChatMessage): string {
  const trace = devreotesTraceForMessage(msg)
  const cited = injectCitationMarkdown(text, trace?.sources)
  return normalizeAssistantMathMarkdown(cited)
}

/** Bust MDCCached when retrieval `sources` arrive so citation tooltips update after streaming. */
function devreotesSourcesCacheKey(msg: ChatMessage): string {
  const s = devreotesTraceForMessage(msg)?.sources
  return s?.length ? s.join('\u0001') : ''
}

function partStateSuffix(part: unknown): string {
  if (!part || typeof part !== 'object') {
    return ''
  }
  if (!('state' in part)) {
    return ''
  }
  const s = (part as { state?: unknown }).state
  return typeof s === 'string' && s.length ? `-${s}` : ''
}

function isPartStreaming(part: unknown): boolean {
  if (!part || typeof part !== 'object') {
    return false
  }
  if (!('state' in part)) {
    return false
  }
  return (part as { state?: unknown }).state !== 'done'
}

const components = {
  pre: ProseStreamPre as unknown as DefineComponent
}

const route = useRoute()
const toast = useToast()
const clipboard = useClipboard()

function getFileName(url: string): string {
  try {
    const urlObj = new URL(url)
    const pathname = urlObj.pathname
    const filename = pathname.split('/').pop() || 'file'
    return decodeURIComponent(filename)
  } catch {
    return 'file'
  }
}

const {
  dropzoneRef,
  isDragging,
  open,
  files,
  isUploading,
  uploadedFiles,
  removeFile,
  clearFiles
} = useFileUploadWithStatus(route.params.id as string)

const { data, refresh: refreshChat } = await useFetch(`/api/chats/${route.params.id}`, {
  cache: 'force-cache'
})
if (!data.value) {
  throw createError({ statusCode: 404, statusMessage: 'Chat not found' })
}
const chatId = data.value.id

const input = ref('')
const { csrf, headerName } = useCsrf()
const messages = ref<ChatMessage[]>((data.value.messages || []) as ChatMessage[])
const chatStatus = ref<'ready' | 'submitted' | 'streaming' | 'error'>('ready')
const chatError = ref<Error | undefined>(undefined)

/** Live retrieval/plan progress for the in-flight assistant message (SSE data-devreotes-progress). */
const streamProgress = ref<DevreotesStreamProgress>(emptyDevreotesStreamProgress())
const streamingAssistantMessageId = ref<string | null>(null)

/** Streamed follow-ups (SSE data-devreotes-followups) until DB row merges trace. */
const followupsBusy = ref(false)
const localFollowups = ref<string[]>([])

const followupChips = computed(() => {
  const last = messages.value[messages.value.length - 1]
  if (!last || last.role !== 'assistant') {
    return []
  }
  const fromTrace = devreotesTraceForMessage(last)?.suggested_followups
  if (fromTrace?.length) {
    return fromTrace
  }
  return localFollowups.value
})

const showDevreotesLoading = computed(() => {
  if (chatStatus.value === 'submitted') {
    return true
  }
  if (chatStatus.value !== 'streaming') {
    return false
  }
  const last = messages.value[messages.value.length - 1]
  if (!last || last.role !== 'assistant') {
    return false
  }
  const text = getTextFromMessage(last)?.trim() ?? ''
  if (text.length > 0) {
    return false
  }
  if (!devreotesProgressIsEmpty(streamProgress.value)) {
    return false
  }
  return true
})

async function runDevreotesTurn(text: string, options: { skipUserInsert?: boolean } = {}) {
  chatStatus.value = 'submitted'
  chatError.value = undefined
  followupsBusy.value = false
  localFollowups.value = []
  streamProgress.value = emptyDevreotesStreamProgress()

  const assistantId = crypto.randomUUID()
  streamingAssistantMessageId.value = assistantId
  // One text part so `#content` has something to render (`parts: []` shows nothing).
  const assistantMessage: ChatMessage = {
    id: assistantId,
    role: 'assistant',
    parts: [{ type: 'text', text: '', state: 'streaming' }]
  }
  messages.value.push(assistantMessage)
  const assistantIndex = messages.value.length - 1

  const patchAssistantText = (next: string, streaming: boolean) => {
    const cur = messages.value[assistantIndex]
    if (!cur) {
      return
    }
    messages.value[assistantIndex] = {
      ...cur,
      parts: [{ type: 'text', text: next, state: streaming ? 'streaming' : 'done' }]
    } as ChatMessage
  }

  try {
    const res = await fetch(`/api/devreotes/chats/${chatId}`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        [headerName]: csrf
      },
      body: JSON.stringify({
        message: text,
        ...(options.skipUserInsert ? { skipUserInsert: true } : {})
      })
    })

    if (!res.ok) {
      const errText = await res.text()
      throw new Error(errText || res.statusText)
    }
    if (!res.body) {
      throw new Error('Empty response body')
    }

    chatStatus.value = 'streaming'

    let acc = ''
    await consumeDevreotesUiSse(
      res.body,
      (delta) => {
        acc += delta
        if (acc.length > 0) {
          streamProgress.value = emptyDevreotesStreamProgress()
        }
        patchAssistantText(acc, true)
      },
      {
        onProgress: (ev) => {
          streamProgress.value = mergeDevreotesProgress(streamProgress.value, ev)
        },
        onFollowups: (ev) => {
          if (ev.kind === 'partial') {
            followupsBusy.value = true
          }
          if (ev.kind === 'done') {
            followupsBusy.value = false
            localFollowups.value = ev.suggestions.filter(s => typeof s === 'string' && s.trim().length > 0)
          }
        }
      }
    )
    patchAssistantText(acc, false)
    streamingAssistantMessageId.value = null
    streamProgress.value = emptyDevreotesStreamProgress()
    // Allow follow-up chips and new prompts while we reconcile messages with the server.
    chatStatus.value = 'ready'

    // Fresh GET (bypasses stale useFetch) + one retry — ensures new assistant row with devreotes_trace exists.
    async function loadServerMessages(): Promise<ChatMessage[] | undefined> {
      const chat = await $fetch<{ messages: ChatMessage[] }>(`/api/chats/${chatId}`, {
        credentials: 'include'
      })
      return chat.messages
    }
    let serverMsgs = await loadServerMessages()
    if (!serverMsgs?.length || serverMsgs.length < messages.value.length) {
      await new Promise(r => setTimeout(r, 400))
      serverMsgs = await loadServerMessages()
    }
    await refreshChat()

    const i = messages.value.length - 1
    const localLast = messages.value[i]
    if (
      serverMsgs?.length
      && serverMsgs.length >= messages.value.length
      && localLast?.role === 'assistant'
    ) {
      const serverLast = serverMsgs[serverMsgs.length - 1]
      if (serverLast?.role === 'assistant') {
        const trace = traceFromRow(serverLast)
        messages.value[i] = {
          ...localLast,
          id: serverLast.id,
          devreotesTrace: trace ?? localLast.devreotesTrace,
          parts: (localLast.parts || []).map((p) => {
            if (p.type === 'text') {
              return { ...p, state: 'done' as const }
            }
            return p
          })
        }
      }
    }
    refreshNuxtData('chats')
  } catch (error: unknown) {
    streamingAssistantMessageId.value = null
    streamProgress.value = emptyDevreotesStreamProgress()
    if (assistantIndex >= 0 && assistantIndex < messages.value.length) {
      messages.value.splice(assistantIndex, 1)
    }
    chatStatus.value = 'error'
    const message
      = error && typeof error === 'object' && 'message' in error
        ? String((error as Error).message)
        : 'Failed to get response from backend.'
    chatError.value = new Error(message)
    toast.add({
      description: message,
      icon: 'i-lucide-alert-circle',
      color: 'error',
      duration: 0
    })
  }
}

async function submitUserText(text: string) {
  const trimmed = text.trim()
  if (!trimmed || isUploading.value || chatStatus.value !== 'ready') {
    return
  }
  const userMessage: ChatMessage = {
    id: crypto.randomUUID(),
    role: 'user',
    parts: [{ type: 'text', text: trimmed }]
  }
  messages.value.push(userMessage)
  input.value = ''
  clearFiles()
  await runDevreotesTurn(trimmed)
}

async function handleSubmit(e: Event) {
  e.preventDefault()
  if (input.value.trim()) {
    await submitUserText(input.value)
  }
}

function onFollowupChipClick(suggestion: string) {
  submitUserText(suggestion)
}

/** Home / suggested-query flow: POST /api/chats only saves the user message; we must run the backend here. */
onMounted(async () => {
  if (messages.value.length !== 1 || messages.value[0]?.role !== 'user') {
    return
  }
  const text = getTextFromMessage(messages.value[0])?.trim()
  if (!text) {
    return
  }
  await runDevreotesTurn(text, { skipUserInsert: true })
})

const copied = ref(false)

function copy(e: MouseEvent, message: ChatMessage) {
  clipboard.copy(getTextFromMessage(message))

  copied.value = true

  setTimeout(() => {
    copied.value = false
  }, 2000)
}

</script>

<template>
  <UDashboardPanel
    id="chat"
    class="relative min-h-0"
    :ui="{ body: 'p-0 sm:p-0 overscroll-none' }"
  >
    <template #header>
      <DashboardNavbar />
    </template>

    <template #body>
      <div ref="dropzoneRef" class="flex flex-1">
        <DragDropOverlay :show="isDragging" />

        <UContainer class="flex-1 flex flex-col gap-4 sm:gap-6">
          <UChatMessages
            should-auto-scroll
            :messages="messages"
            :status="chatStatus"
            :assistant="{ actions: [{ label: 'Copy', icon: copied ? 'i-lucide-copy-check' : 'i-lucide-copy', onClick: copy }] }"
            :spacing-offset="160"
            class="lg:pt-(--ui-header-height) pb-4 sm:pb-6"
          >
            <template #content="{ message }">
              <div
                v-if="message.role === 'assistant' && message.id === streamingAssistantMessageId"
                class="w-full min-w-0 max-w-full"
              >
                <DevreotesProgressStrip :progress="streamProgress" />
              </div>
              <template v-for="(part, index) in message.parts" :key="`${message.id}-${part.type}-${index}${partStateSuffix(part)}`">
                <Reasoning
                  v-if="part.type === 'reasoning'"
                  :text="part.text"
                  :is-streaming="isPartStreaming(part)"
                />
                <!-- Only render markdown for assistant messages to prevent XSS from user input -->
                <MDCCached
                  v-else-if="part.type === 'text' && message.role === 'assistant'"
                  :key="`${message.id}-${index}-${devreotesSourcesCacheKey(message)}`"
                  :value="assistantMarkdownWithCitations(part.text, message)"
                  :cache-key="`${message.id}-${index}-${devreotesSourcesCacheKey(message)}`"
                  :components="components"
                  :parser-options="{ highlight: false }"
                  class="prose prose-sm dark:prose-invert max-w-none *:first:mt-0 *:last:mb-0"
                />
                <!-- User messages are rendered as plain text (safely escaped by Vue) -->
                <p v-else-if="part.type === 'text' && message.role === 'user'" class="whitespace-pre-wrap">
                  {{ part.text }}
                </p>
                <ToolWeather
                  v-else-if="part.type === 'tool-weather'"
                  :invocation="(part as WeatherUIToolInvocation)"
                />
                <ToolChart
                  v-else-if="part.type === 'tool-chart'"
                  :invocation="(part as ChartUIToolInvocation)"
                />
                <FileAvatar
                  v-else-if="part.type === 'file'"
                  :name="getFileName(part.url)"
                  :type="part.mediaType"
                  :preview-url="part.url"
                  class="inline-flex"
                />
              </template>
              <!-- <DevreotesTracePanel
                v-if="message.role === 'assistant' && devreotesTraceForMessage(message)"
                :trace="devreotesTraceForMessage(message)!"
              /> -->
            </template>
          </UChatMessages>

          <div
            v-if="followupChips.length > 0 || followupsBusy"
            class="flex flex-wrap gap-2 px-1 -mt-1 pb-1 max-w-full"
          >
            <span
              v-if="followupsBusy && followupChips.length === 0"
              class="text-xs text-muted flex items-center gap-1.5 w-full"
            >
              <span class="i-lucide-sparkles size-3.5 shrink-0 animate-pulse" aria-hidden="true" />
              <img
                src="/suggestion.gif"
                alt=""
                width="32"
                height="32"
                class="shrink-0 rounded-sm"
                aria-hidden="true"
              />
              Thinking of a few great follow-ups you can ask next…
            </span>
            <span
              v-else-if="followupChips.length > 0"
              class="text-xs text-muted flex items-center gap-1.5 w-full"
            >
              Want to go deeper? Here are follow-ups :
            </span>
            <UButton
              v-for="(q, qi) in followupChips"
              :key="`${qi}-${q.slice(0, 32)}`"
              variant="outline"
              color="neutral"
              size="xs"
              class="text-left font-normal max-w-full whitespace-normal h-auto py-1.5"
              :label="q"
              @click="onFollowupChipClick(q)"
            />
          </div>

          <div
            v-if="showDevreotesLoading"
            class="flex items-center gap-3 px-1 text-muted -mt-2 sm:-mt-3"
            aria-live="polite"
          >
            <img
              src="/reading-read.gif"
              alt=""
              width="48"
              height="48"
              class="h-12 w-12 shrink-0 object-contain rounded-md"
            >
            <span class="text-sm text-[var(--ui-text-muted)]">Searching the corpus…</span>
          </div>

          <UChatPrompt
            v-model="input"
            :error="chatError"
            :disabled="isUploading"
            variant="subtle"
            class="sticky bottom-0 [view-transition-name:chat-prompt] rounded-b-none z-10"
            :ui="{ base: 'px-1.5' }"
            @submit="handleSubmit"
          >
            <template v-if="files.length > 0" #header>
              <div class="flex flex-wrap gap-2">
                <FileAvatar
                  v-for="fileWithStatus in files"
                  :key="fileWithStatus.id"
                  :name="fileWithStatus.file.name"
                  :type="fileWithStatus.file.type"
                  :preview-url="fileWithStatus.previewUrl"
                  :status="fileWithStatus.status"
                  :error="fileWithStatus.error"
                  removable
                  @remove="removeFile(fileWithStatus.id)"
                />
              </div>
            </template>

            <template #footer>
              <div class="flex items-center gap-1">
                <FileUploadButton :open="open" />
              </div>

              <UChatPromptSubmit
                :status="chatStatus"
                :disabled="isUploading"
                color="neutral"
                size="sm"
              />
            </template>
          </UChatPrompt>
        </UContainer>
      </div>
    </template>
  </UDashboardPanel>
</template>
