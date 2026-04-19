/**
 * useGlobalAgent — platform-wide agent chat composable.
 *
 * Derives context from the current Vue Router route, manages chat state,
 * and exposes `agentPanels` for sidebar integration when on the classify page.
 *
 * Mount once in App.vue; ClassifyView injects the `agentPanels` ref via
 * provide/inject.
 */

import { ref, computed, watch, provide, type InjectionKey, type Ref } from 'vue'
import { useRoute } from 'vue-router'
import type { ChatEntry, AgentPanelDescriptor, AgentContext } from '../types'
import { streamGlobalAgentChat } from '../api'
import { useAuthStore } from '../stores/auth'

export type AgentChatStatus = 'idle' | 'streaming' | 'error'

/** Injection key for ClassifyView to read agent panels. */
export const GLOBAL_AGENT_PANELS_KEY: InjectionKey<Ref<AgentPanelDescriptor[]>> =
  Symbol('globalAgentPanels')

/** Injection key so child views know the global agent send function. */
export const GLOBAL_AGENT_SEND_KEY: InjectionKey<(message: string) => Promise<void>> =
  Symbol('globalAgentSend')

export interface UseGlobalAgentReturn {
  /** Chat message history. */
  messages: Ref<ChatEntry[]>
  /** Current streaming status. */
  status: Ref<AgentChatStatus>
  /** Agent-controlled panels (populated when on classify page). */
  agentPanels: Ref<AgentPanelDescriptor[]>
  /** Send a user message. */
  send: (message: string) => Promise<void>
  /** Abort the current stream. */
  abort: () => void
  /** Clear chat history and panels. */
  clearHistory: () => void
}

let _idCounter = 0
function nextId(): string {
  return `gchat-${++_idCounter}-${Date.now()}`
}

export function useGlobalAgent(): UseGlobalAgentReturn {
  const route = useRoute()
  const authStore = useAuthStore()

  const messages = ref<ChatEntry[]>([])
  const status = ref<AgentChatStatus>('idle')
  const agentPanels = ref<AgentPanelDescriptor[]>([])
  let abortController: AbortController | null = null

  // Derive a stable session ID from the user
  const sessionId = computed(() => `global-${authStore.user?.id ?? 'anon'}`)

  // Build context from the current route
  function buildContext(): AgentContext {
    const path = route.path
    const params = route.params

    const ctx: AgentContext = {
      page: path,
    }

    // Extract entity IDs from route params
    if (path.includes('/datasets/') && params.id) {
      ctx.dataset_id = String(params.id)
    }
    if (path.includes('/jobs/') && params.id) {
      ctx.job_id = String(params.id)
    }
    if (path.includes('/schedules/') && params.id) {
      ctx.schedule_id = String(params.id)
    }

    return ctx
  }

  // Clear agent panels when navigating away from classify page
  watch(
    () => route.path,
    (newPath) => {
      if (!newPath.includes('/classify')) {
        agentPanels.value = []
      }
    },
  )

  async function send(userMessage: string) {
    if (!userMessage.trim()) return
    if (status.value === 'streaming') return

    // Add user message to history
    messages.value = [
      ...messages.value,
      {
        id: nextId(),
        role: 'user',
        content: userMessage,
        timestamp: Date.now(),
      },
    ]

    status.value = 'streaming'
    abortController = new AbortController()

    let assistantContent = ''
    const assistantId = nextId()

    try {
      const context = buildContext()
      const request = {
        message: userMessage,
        context,
        session_id: sessionId.value,
      }

      for await (const frame of streamGlobalAgentChat(request, abortController.signal)) {
        if (frame.event === 'agent-message') {
          const data = JSON.parse(frame.data)
          assistantContent += data.content ?? ''
          // Upsert the assistant message
          const existing = messages.value.find((m) => m.id === assistantId)
          if (existing) {
            existing.content = assistantContent
            messages.value = [...messages.value]
          } else {
            messages.value = [
              ...messages.value,
              {
                id: assistantId,
                role: 'assistant',
                content: assistantContent,
                timestamp: Date.now(),
              },
            ]
          }
        } else if (frame.event === 'agent-action') {
          const data = JSON.parse(frame.data)
          messages.value = [
            ...messages.value,
            {
              id: nextId(),
              role: 'action',
              content: data.summary,
              tool: data.tool,
              timestamp: Date.now(),
            },
          ]
        } else if (frame.event === 'sidebar-update') {
          const data = JSON.parse(frame.data)
          if (Array.isArray(data.panels)) {
            agentPanels.value = data.panels
          }
        } else if (frame.event === 'done') {
          // Stream complete
        }
      }
      status.value = 'idle'
    } catch (e) {
      if ((e as Error).name === 'AbortError') {
        status.value = 'idle'
      } else {
        status.value = 'error'
        messages.value = [
          ...messages.value,
          {
            id: nextId(),
            role: 'assistant',
            content: `Error: ${e instanceof Error ? e.message : String(e)}`,
            timestamp: Date.now(),
          },
        ]
      }
    } finally {
      abortController = null
    }
  }

  function abort() {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
  }

  function clearHistory() {
    messages.value = []
    agentPanels.value = []
    status.value = 'idle'
  }

  // Provide agent panels for child views to inject
  provide(GLOBAL_AGENT_PANELS_KEY, agentPanels)
  provide(GLOBAL_AGENT_SEND_KEY, send)

  return {
    messages,
    status,
    agentPanels,
    send,
    abort,
    clearHistory,
  }
}
