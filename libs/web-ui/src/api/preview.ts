import { req } from "./client";

export interface PreviewSession {
  id: string;
  name: string;
  dataset_type: string;
  total_items: number;
  created_at: string;
}

export interface PreviewItem {
  id: string;
  image_uris: string[];
  metadata: Record<string, unknown>;
}

export interface PreviewItemsPage {
  items: PreviewItem[];
  next_cursor: string | null;
  total: number;
}

export interface PreviewPersistScope {
  dataset_name: string;
  ls_project_name?: string | null;
}

export interface PreviewPersistStatus {
  status: string;
  dataset_id?: string | null;
  imported_count?: number;
  error?: string | null;
}

export function createPreviewSession(body: {
  name: string;
  dataset_type: string;
}): Promise<PreviewSession> {
  return req<PreviewSession>("/preview/sessions", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getPreviewSession(
  sessionId: string,
): Promise<PreviewSession> {
  return req<PreviewSession>(`/preview/sessions/${sessionId}`);
}

export function listPreviewItems(
  sessionId: string,
  cursor?: string | null,
  limit?: number,
): Promise<PreviewItemsPage> {
  const params = new URLSearchParams();
  if (cursor) params.set("cursor", cursor);
  if (limit !== undefined) params.set("limit", String(limit));
  const qs = params.toString() ? `?${params.toString()}` : "";
  return req<PreviewItemsPage>(
    `/preview/sessions/${sessionId}/items${qs}`,
  );
}

export function startPreviewPersist(
  sessionId: string,
  scope: PreviewPersistScope,
): Promise<PreviewPersistStatus> {
  return req<PreviewPersistStatus>(
    `/preview/sessions/${sessionId}/persist`,
    {
      method: "POST",
      body: JSON.stringify(scope),
    },
  );
}

export function getPreviewPersistStatus(
  sessionId: string,
): Promise<PreviewPersistStatus> {
  return req<PreviewPersistStatus>(
    `/preview/sessions/${sessionId}/persist`,
  );
}
