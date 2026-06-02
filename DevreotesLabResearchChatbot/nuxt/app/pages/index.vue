<script setup lang="ts">
const input = ref('')
const loading = ref(false)
/** New chat id for POST /api/chats and file uploads; rotated after each successful new chat. */
const chatId = ref(crypto.randomUUID())

const {
  dropzoneRef,
  isDragging,
  open,
  files,
  isUploading,
  uploadedFiles,
  removeFile,
  clearFiles
} = useFileUploadWithStatus(chatId)

const { csrf, headerName } = useCsrf()

async function createChat(prompt: string) {
  input.value = prompt
  loading.value = true

  try {
    const parts: Array<{ type: string, text?: string, mediaType?: string, url?: string }> = [{ type: 'text', text: prompt }]

    if (uploadedFiles.value.length > 0) {
      parts.push(...uploadedFiles.value)
    }

    const chat = await $fetch('/api/chats', {
      method: 'POST',
      headers: { [headerName]: csrf },
      body: {
        id: chatId.value,
        message: {
          role: 'user',
          parts
        }
      }
    })

    refreshNuxtData('chats')
    await navigateTo(`/chat/${chat?.id}`)
    chatId.value = crypto.randomUUID()
  } finally {
    loading.value = false
  }
}

async function onSubmit() {
  await createChat(input.value)
  clearFiles()
}

// Sample questions aligned with chatBot/resources/devreotes_demo.html (Suggested Queries)
const quickChats = [
  {
    label: 'What is the LEGI model and how does it explain chemotaxis?',
    icon: 'i-lucide-microscope'
  },
  {
    label: 'How does PTEN regulate cell polarity and directed migration?',
    icon: 'i-lucide-flask-conical'
  },
  {
    label: 'How do excitable networks drive spontaneous cell migration?',
    icon: 'i-lucide-zap'
  },
  {
    label: 'What experimental methods recur across the corpus?',
    icon: 'i-lucide-bar-chart-2'
  },
  {
    label: 'Which papers should a newcomer to chemotaxis read first?',
    icon: 'i-lucide-book-open'
  },
  {
    label: 'Which genes are mentioned most often across the corpus?',
    icon: 'i-lucide-map'
  },
  {
    label: 'Which collaborators appear across multiple papers?',
    icon: 'i-lucide-users'
  },
  {
    label: 'What molecules form the spatial compass inside a migrating cell?',
    icon: 'i-lucide-compass'
  }
]
</script>

<template>
  <UDashboardPanel
    id="home"
    class="min-h-0"
    :ui="{ body: 'p-0 sm:p-0' }"
  >
    <template #header>
      <DashboardNavbar />
    </template>

    <template #body>
      <div ref="dropzoneRef" class="flex flex-1">
        <DragDropOverlay :show="isDragging" />

        <UContainer class="flex-1 flex flex-col justify-center gap-4 sm:gap-6 py-8">
          <div class="text-center max-w-[460px] mx-auto devreotes-welcome">
            <span class="text-5xl block mb-5" aria-hidden="true">🧬</span>
            <h1
              class="text-2xl sm:text-[28px] leading-tight text-highlighted font-devreotes-display mb-3"
            >
              Ask the Research Corpus
            </h1>
            <p class="text-sm text-muted leading-relaxed">
              This assistant answers questions about Prof. Peter Devreotes&apos; lab research at
              Johns Hopkins — chemotaxis, signal transduction, cell polarity, and excitable networks.
              Responses cite only the loaded papers.
            </p>
            <p class="text-sm text-muted leading-relaxed mt-4">
              Type a question below or pick a suggested query.
            </p>
          </div>

          <UChatPrompt
            v-model="input"
            placeholder="Ask about Prof. Devreotes' research…"
            :status="loading ? 'streaming' : 'ready'"
            :disabled="isUploading"
            class="[view-transition-name:chat-prompt]"
            variant="subtle"
            :ui="{ base: 'px-1.5' }"
            @submit="onSubmit"
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

                <ModelSelect />
              </div>

              <UChatPromptSubmit color="neutral" size="sm" :disabled="isUploading" />
            </template>
          </UChatPrompt>

          <div class="flex flex-wrap gap-2">
            <UButton
              v-for="quickChat in quickChats"
              :key="quickChat.label"
              :icon="quickChat.icon"
              :label="quickChat.label"
              size="sm"
              color="neutral"
              variant="outline"
              class="rounded-full"
              @click="createChat(quickChat.label)"
            />
          </div>
        </UContainer>
      </div>
    </template>
  </UDashboardPanel>
</template>
