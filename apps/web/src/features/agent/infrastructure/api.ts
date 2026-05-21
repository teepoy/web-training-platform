import { ApiError, getApiBase, getAuthToken, req } from "@/shared/api/client";
import type { GlobalChatRequest, SurfaceStateDocument, AgentPanelDescriptor } from '@/shared/api/types';
import type { SSEFrame } from '@/shared/api/sse';

export function getSurfaceState(
  sessionId: string,
  surfaceId: string,
): Promise<SurfaceStateDocument> {
  return req(`/sessions/${sessionId}/surfaces/${surfaceId}`);
}

export function setSurfacePanel(
  sessionId: string,
  surfaceId: string,
  panel: AgentPanelDescriptor,
): Promise<SurfaceStateDocument> {
  return req(`/sessions/${sessionId}/surfaces/${surfaceId}/panels`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ panel }),
  });
}

export function removeSurfacePanel(
  sessionId: string,
  surfaceId: string,
  panelId: string,
): Promise<SurfaceStateDocument> {
  return req(`/sessions/${sessionId}/surfaces/${surfaceId}/panels/${panelId}`, {
    method: "DELETE",
  });
}

export function exportSurfaceState(
  sessionId: string,
  surfaceId: string,
): Promise<SurfaceStateDocument> {
  return req(`/sessions/${sessionId}/surfaces/${surfaceId}/export`);
}

export function importSurfaceState(
  sessionId: string,
  surfaceId: string,
  doc: SurfaceStateDocument,
): Promise<SurfaceStateDocument> {
  return req(`/sessions/${sessionId}/surfaces/${surfaceId}/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(doc),
  });
}

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

  const reader = resp.body?.getReader();
  if (!reader) {
    throw new ApiError("Agent stream response did not include a body", resp.status);
  }
  yield* parseSSEStream(reader);
}
