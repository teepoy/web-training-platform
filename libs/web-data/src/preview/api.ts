import { req } from "../client/apiClient";

export interface PreviewSession {
  session_id: string;
  collection_ref: string;
  classification_enabled: boolean;
  estimated_total: number | null;
  loaded_count: number;
  next_cursor: string | null;
  has_more: boolean;
}

export interface PreviewItem {
  upstream_item_id: string;
  image_uris: string[];
  metadata: Record<string, unknown>;
}

export interface PreviewItemsPage {
  items: PreviewItem[];
  next_cursor: string | null;
  has_more: boolean;
  estimated_total: number | null;
}

export type PreviewPersistScope = "entire_collection" | "loaded_items_only";

export interface PreviewPersistStatus {
  dataset_id: string;
  persist_session_id: string;
  status: "pending" | "running" | "completed" | "failed";
  imported_count: number;
  remaining_count: number;
  error: string | null;
}

export function createPreviewSession(collectionRef: string): Promise<PreviewSession> {
  return req<PreviewSession>("/preview-sessions", {
    method: "POST",
    body: JSON.stringify({ collection_ref: collectionRef }),
  });
}

export function getPreviewSession(sessionId: string): Promise<PreviewSession> {
  return req<PreviewSession>(`/preview-sessions/${sessionId}`);
}

export function listPreviewItems(
  sessionId: string,
  cursor: string | null,
  limit: number,
): Promise<PreviewItemsPage> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set("cursor", cursor);
  return req<PreviewItemsPage>(
    `/preview-sessions/${sessionId}/items?${params}`,
  );
}

export function startPreviewPersist(
  sessionId: string,
  scope: PreviewPersistScope,
): Promise<PreviewPersistStatus> {
  return req<PreviewPersistStatus>(`/preview-sessions/${sessionId}/persist`, {
    method: "POST",
    body: JSON.stringify({ scope }),
  });
}

export function getPreviewPersistStatus(sessionId: string): Promise<PreviewPersistStatus> {
  return req<PreviewPersistStatus>(`/preview-sessions/${sessionId}/persist-status`);
}
