import { req, getApiBase, getAuthToken, ApiError } from "../client/apiClient";

export interface AgentPanelDescriptor {
  id: string;
  component: string;
  title: string;
  order: number;
  collapsed: boolean;
  size: "compact" | "normal" | "large";
  data: Record<string, unknown> | null;
  data_source: {
    kind: "api";
    endpoint: string;
    params: Record<string, string>;
    refresh_interval: number;
  } | {
    kind: "context";
    key: string;
    path: string | null;
  } | null;
  config: Record<string, unknown>;
  ephemeral: boolean;
  ttl: number | null;
}

export interface SurfaceStateDocument {
  version: number;
  surface_id: string;
  panels: AgentPanelDescriptor[];
  layout: { width: number; position: "right" | "left" };
  exported_at: string | null;
  metadata: Record<string, unknown>;
}

export interface AgentContext {
  page: string;
  dataset_id?: string | null;
  job_id?: string | null;
  schedule_id?: string | null;
  extra?: Record<string, unknown>;
}

export interface GlobalChatRequest {
  message: string;
  context: AgentContext;
  session_id?: string | null;
}

export interface WaferPointsQueryResponse {
  points: Array<{ id: string; x: number; y: number; value?: number }>;
  total: number;
}

export function getSurfaceState(sessionId: string, surfaceId: string): Promise<SurfaceStateDocument> {
  return req(`/sessions/${sessionId}/surfaces/${surfaceId}`);
}

export function setSurfacePanel(
  sessionId: string,
  surfaceId: string,
  panel: AgentPanelDescriptor,
): Promise<SurfaceStateDocument> {
  return req(`/sessions/${sessionId}/surfaces/${surfaceId}/panels`, {
    method: "POST",
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

export function exportSurfaceState(sessionId: string, surfaceId: string): Promise<SurfaceStateDocument> {
  return req(`/sessions/${sessionId}/surfaces/${surfaceId}/export`);
}

export function importSurfaceState(
  sessionId: string,
  surfaceId: string,
  doc: SurfaceStateDocument,
): Promise<SurfaceStateDocument> {
  return req(`/sessions/${sessionId}/surfaces/${surfaceId}/import`, {
    method: "POST",
    body: JSON.stringify(doc),
  });
}

export function queryDatasetData<T = Record<string, unknown>>(
  datasetId: string,
  queryType: string,
  params: Record<string, unknown> = {},
): Promise<T> {
  return req<T>(`/datasets/${datasetId}/query`, {
    method: "POST",
    body: JSON.stringify({ query_type: queryType, params }),
  });
}

export function queryWaferPoints(datasetId: string): Promise<WaferPointsQueryResponse> {
  return queryDatasetData<WaferPointsQueryResponse>(datasetId, "wafer-points");
}

// ---------------------------------------------------------------------------
// SSE streaming helpers
// ---------------------------------------------------------------------------

/** Parsed SSE frame from a POST-based SSE response stream. */
export interface SSEFrame {
  event: string;
  data: string;
}

/**
 * Shared SSE parser: reads a ReadableStream into async SSE frames.
 * Used by both per-dataset agent chat and global agent chat.
 */
async function* parseSSEStream(
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

function buildSSEHeaders(): Record<string, string> {
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
 * POST-based SSE streaming for per-dataset agent chat.
 * Returns an async generator of parsed SSE events.
 */
export async function* streamAgentChat(
  datasetId: string,
  userMessage: string,
  signal?: AbortSignal,
): AsyncGenerator<SSEFrame> {
  const resp = await fetch(`${getApiBase()}/datasets/${datasetId}/agent/chat`, {
    method: "POST",
    headers: buildSSEHeaders(),
    body: JSON.stringify({ message: userMessage }),
    signal,
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new ApiError(text || resp.statusText, resp.status);
  }

  const reader = resp.body!.getReader();
  yield* parseSSEStream(reader);
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
