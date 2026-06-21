// ---------------------------------------------------------------------------
// Shared SSE (Server-Sent Events) primitives for POST-based streaming.
// Canonical source for SSEFrame, parseSSEStream, buildSSEHeaders, and
// streamGlobalAgentChat.
// Also includes EventSource-based helpers for job/task streaming.
// ---------------------------------------------------------------------------

import { getApiBase, getAuthToken, getOrgId, ApiError } from "./client";
import type { GlobalChatRequest } from "@/generated/orval/models";

/** Parsed SSE frame from a POST-based SSE response stream. */
export interface SSEFrame {
  event: string;
  data: string;
}

/**
 * Shared SSE parser: reads a ReadableStream into async SSE frames.
 * Used by both per-dataset agent chat and global agent chat.
 */
export async function* parseSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
): AsyncGenerator<SSEFrame> {
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

export function buildSSEHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const token = getAuthToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

/**
 * POST-based SSE streaming for the global agent chat.
 * Returns an async generator of parsed SSE events.
 */
export async function* streamGlobalAgentChat(
  request: GlobalChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<SSEFrame> {
  const resp = await fetch(`${getApiBase()}/agent/chat`, {
    method: "POST",
    headers: buildSSEHeaders(),
    body: JSON.stringify(request),
    signal,
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new ApiError(text || resp.statusText, resp.status);
  }

  const reader = resp.body!.getReader();
  yield* parseSSEStream(reader);
}

export function buildTrackedTaskEventSource(taskId: string): EventSource {
  const params = new URLSearchParams();
  const token = getAuthToken();
  if (token) {
    params.set("token", token);
  }
  return new EventSource(
    `${getApiBase()}/task-tracker/tasks/${taskId}/stream?${params.toString()}`,
  );
}

export interface ApiSseEvent {
  event_type: string;
  status?: string;
  message?: string;
  operation?: string;
  error?: string;
  dataset_id?: string;
  imported_count?: number;
  loaded_count?: number;
  total_count?: number;
  payload?: Record<string, unknown>;
  uri?: string;
  rows?: number;
}

export interface StreamApiSseOptions {
  method?: "GET" | "POST";
  body?: unknown;
  onEvent?: (event: ApiSseEvent) => void;
}

function parseApiSseData(data: string): ApiSseEvent {
  return JSON.parse(data) as ApiSseEvent;
}

export async function streamApiSse(
  path: string,
  options: StreamApiSseOptions = {},
): Promise<ApiSseEvent | null> {
  const headers = buildSSEHeaders();
  headers.Accept = "text/event-stream";
  const orgId = getOrgId();
  if (orgId) headers["X-Organization-ID"] = orgId;
  let body: BodyInit | undefined;
  if (options.body !== undefined) {
    body = JSON.stringify(options.body);
  }

  const response = await fetch(`${getApiBase()}${path}`, {
    method: options.method ?? (body ? "POST" : "GET"),
    headers,
    body,
  });
  if (!response.ok) {
    let detail = `request failed: ${response.status}`;
    try {
      const parsed = await response.json();
      detail =
        typeof parsed?.detail === "string" ? parsed.detail : JSON.stringify(parsed);
    } catch {}
    throw new ApiError(detail, response.status);
  }
  if (!response.body) {
    throw new Error("SSE response body is not readable");
  }

  let dataEvent: ApiSseEvent | null = null;
  for await (const frame of parseSSEStream(response.body.getReader())) {
    const event = parseApiSseData(frame.data);
    options.onEvent?.(event);
    if (event.event_type === "error") {
      throw new Error(event.error || "stream failed");
    }
    if (event.event_type === "data") {
      dataEvent = event;
    }
  }
  return dataEvent;
}
