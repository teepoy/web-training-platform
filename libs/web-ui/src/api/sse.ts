// ---------------------------------------------------------------------------
// Shared SSE (Server-Sent Events) primitives for POST-based streaming.
// Canonical source for SSEFrame, parseSSEStream, buildSSEHeaders, and
// streamGlobalAgentChat.
// ---------------------------------------------------------------------------

import { getApiBase, getAuthToken, ApiError } from "./client";
import type { GlobalChatRequest } from "./types";

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
    headers["Authorization"] = `Bearer ${token}`;
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
