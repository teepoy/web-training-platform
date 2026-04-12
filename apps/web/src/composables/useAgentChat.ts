/**
 * useAgentChat — manages the agent chat conversation over POST-based SSE.
 *
 * Sends user messages to the backend, streams responses, and emits
 * sidebar-update events to the surface composable.
 */

import { ref, shallowRef, type Ref } from 'vue'
import type { ChatEntry, AgentPanelDescriptor } from '../types'
import { streamAgentChat } from '../api'

export type AgentChatStatus = 'idle' | 'streaming' | 'error'

export interface UseAgentChatReturn {
  /** Chat message history. */
  messages: Ref<ChatEntry[]>
  /** Current status. */
  status: Ref<AgentChatStatus>
  /** Send a user message and stream the response. */
  send: (message: string) => Promise<void>
  /** Abort the current stream. */
  abort: () => void
  /** Clear chat history. */
  clearHistory: () => void
}

let _idCounter = 0
function nextId(): string {
  return `chat-${++_idCounter}-${Date.now()}`
}

export function useAgentChat(
  datasetId: string,
  options?: {
    onSidebarUpdate?: (panels: AgentPanelDescriptor[]) => void
  },
): UseAgentChatReturn {
  const messages = ref<ChatEntry[]>([])
  const status = ref<AgentChatStatus>('idle')
  let abortController: AbortController | null = null

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
      for await (const frame of streamAgentChat(datasetId, userMessage, abortController.signal)) {
        if (frame.event === 'agent-message') {
          const data = JSON.parse(frame.data)
          assistantContent += data.content ?? ''
          // Upsert the assistant message
          const existing = messages.value.find(m => m.id === assistantId)
          if (existing) {
            existing.content = assistantContent
            // Trigger reactivity
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
          if (options?.onSidebarUpdate && Array.isArray(data.panels)) {
            options.onSidebarUpdate(data.panels)
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
    status.value = 'idle'
  }

  return {
    messages,
    status,
    send,
    abort,
    clearHistory,
  }
}
