/**
 * useAgentCore — shared agent chat state machine.
 *
 * Transport-agnostic core: SSE frame iteration, message accumulation,
 * abort-controller management, and status transitions.
 *
 * App-specific wiring (route context, auth session, panel orchestration)
 * lives in the app-layer adapter.
 */

import { ref, type Ref } from "vue";
import type { ChatEntry, AgentChatStatus } from "../types/components";

/** Minimal parsed SSE frame — fine for core logic. */
export interface SSEFrame {
  event: string;
  data: string;
}

export interface UseAgentCoreOptions {
  /**
   * Stream factory: receives the user message and an AbortSignal,
   * returns an async generator of parsed SSE frames.
   */
  stream: (message: string, signal: AbortSignal) => AsyncGenerator<SSEFrame>;
  /**
   * Optional callback for every SSE frame the core sees.
   * The adapter uses this to intercept sidebar-update events.
   */
  onFrame?: (frame: SSEFrame) => void;
}

export interface UseAgentCoreReturn {
  /** Chat message history (user, assistant, action). */
  messages: Ref<ChatEntry[]>;
  /** Current streaming status. */
  status: Ref<AgentChatStatus>;
  /** Send a user message and start streaming. */
  send: (message: string) => Promise<void>;
  /** Abort the current stream. */
  abort: () => void;
  /** Clear chat history and reset status. */
  clearHistory: () => void;
}

// ── internal helpers ──────────────────────────────────────────

let _idCounter = 0;
function nextId(): string {
  return `gchat-${++_idCounter}-${Date.now()}`;
}

// ── composable ─────────────────────────────────────────────────

export function useAgentCore(
  options: UseAgentCoreOptions,
): UseAgentCoreReturn {
  const { stream, onFrame } = options;

  const messages = ref<ChatEntry[]>([]);
  const status = ref<AgentChatStatus>("idle");
  let abortController: AbortController | null = null;

  async function send(userMessage: string) {
    if (!userMessage.trim()) return;
    if (status.value === "streaming") return;

    // Push user message
    messages.value = [
      ...messages.value,
      {
        id: nextId(),
        role: "user",
        content: userMessage,
        timestamp: Date.now(),
      },
    ];

    status.value = "streaming";
    abortController = new AbortController();

    let assistantContent = "";
    const assistantId = nextId();

    try {
      for await (const frame of stream(userMessage, abortController.signal)) {
        // Let the adapter observe every frame
        onFrame?.(frame);

        if (frame.event === "agent-message") {
          const data = JSON.parse(frame.data);
          assistantContent += data.content ?? "";

          // Upsert the assistant message
          const existing = messages.value.find((m) => m.id === assistantId);
          if (existing) {
            existing.content = assistantContent;
            messages.value = [...messages.value];
          } else {
            messages.value = [
              ...messages.value,
              {
                id: assistantId,
                role: "assistant",
                content: assistantContent,
                timestamp: Date.now(),
              },
            ];
          }
        } else if (frame.event === "agent-action") {
          const data = JSON.parse(frame.data);
          messages.value = [
            ...messages.value,
            {
              id: nextId(),
              role: "action",
              content: data.summary,
              tool: data.tool,
              timestamp: Date.now(),
            },
          ];
        }
        // "done" / "sidebar-update" / other events are forwarded via onFrame
      }

      status.value = "idle";
    } catch (e) {
      if ((e as Error).name === "AbortError") {
        status.value = "idle";
      } else {
        status.value = "error";
        messages.value = [
          ...messages.value,
          {
            id: nextId(),
            role: "assistant",
            content: `Error: ${e instanceof Error ? e.message : String(e)}`,
            timestamp: Date.now(),
          },
        ];
      }
    } finally {
      abortController = null;
    }
  }

  function abort() {
    if (abortController) {
      abortController.abort();
      abortController = null;
    }
  }

  function clearHistory() {
    messages.value = [];
    status.value = "idle";
  }

  return { messages, status, send, abort, clearHistory };
}
