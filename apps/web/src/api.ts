import type { GlobalChatRequest } from "./types";
import type { ApiError as ApiErrorType } from "./types";
import { getStoredToken, useAuthStore } from "./stores/auth";

export const API_BASE = import.meta.env.VITE_API_BASE || "/api/v1";
export const HEALTH_URL = import.meta.env.VITE_HEALTH_URL || "/api/v1/health";

// ---------------------------------------------------------------------------
// Typed error class
// ---------------------------------------------------------------------------

export class ApiError extends Error implements ApiErrorType {
  detail: string;
  status: number;

  constructor(detail: string, status: number) {
    super(`API ${status}: ${detail}`);
    this.detail = detail;
    this.status = status;
  }
}

function getAuthContext(): { token: string | null; authEnabled: boolean } {
  try {
    const authStore = useAuthStore();
    const authEnabled = authStore.authEnabled;
    return {
      token: authEnabled ? (authStore.token ?? getStoredToken()) : null,
      authEnabled,
    };
  } catch {
    return {
      token: getStoredToken(),
      authEnabled: true,
    };
  }
}

// ---------------------------------------------------------------------------
// SSE helpers
// ---------------------------------------------------------------------------

export function buildJobEventSource(jobId: string): EventSource {
  let tokenParam = "";
  try {
    const { token } = getAuthContext();
    if (token) {
      tokenParam = `?token=${encodeURIComponent(token)}`;
    }
  } catch {
    /* ignore */
  }
  return new EventSource(
    `${API_BASE}/training-jobs/${jobId}/events${tokenParam}`,
  );
}

export function buildTrackedTaskEventSource(taskId: string): EventSource {
  let tokenParam = "";
  try {
    const { token } = getAuthContext();
    if (token) {
      tokenParam = `?token=${encodeURIComponent(token)}`;
    }
  } catch {
    /* ignore */
  }
  return new EventSource(
    `${API_BASE}/task-tracker/tasks/${taskId}/stream${tokenParam}`,
  );
}

/**
 * Send a chat message to the agent and return an EventSource for SSE streaming.
 * The caller must close the EventSource when done.
 */
export function sendAgentChat(
  datasetId: string,
  message: string,
): { eventSource: EventSource; abort: () => void } {
  const controller = new AbortController();
  const { token } = getAuthContext();

  const url = `${API_BASE}/datasets/${datasetId}/agent/chat`;

  return {
    eventSource: null as unknown as EventSource,
    abort: () => controller.abort(),
  };
}

/**
 * POST-based SSE streaming for agent chat.
 * Returns an async generator of parsed SSE events.
 */
export async function* streamAgentChat(
  datasetId: string,
  userMessage: string,
  signal?: AbortSignal,
): AsyncGenerator<{ event: string; data: string }> {
  const { token } = getAuthContext();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const resp = await fetch(`${API_BASE}/datasets/${datasetId}/agent/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify({ message: userMessage }),
    signal,
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new ApiError(text || resp.statusText, resp.status);
  }

  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    let currentEvent = "message";
    let currentData = "";

    for (const line of lines) {
      if (line.startsWith("event: ")) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        currentData = line.slice(6);
      } else if (line === "") {
        if (currentData) {
          yield { event: currentEvent, data: currentData };
        }
        currentEvent = "message";
        currentData = "";
      }
    }
  }
}

/**
 * POST-based SSE streaming for the global agent chat.
 * Returns an async generator of parsed SSE events.
 */
export async function* streamGlobalAgentChat(
  request: GlobalChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<{ event: string; data: string }> {
  const { token } = getAuthContext();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const resp = await fetch(`${API_BASE}/agent/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify(request),
    signal,
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new ApiError(text || resp.statusText, resp.status);
  }

  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    let currentEvent = "message";
    let currentData = "";

    for (const line of lines) {
      if (line.startsWith("event: ")) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        currentData = line.slice(6);
      } else if (line === "") {
        if (currentData) {
          yield { event: currentEvent, data: currentData };
        }
        currentEvent = "message";
        currentData = "";
      }
    }
  }
}
