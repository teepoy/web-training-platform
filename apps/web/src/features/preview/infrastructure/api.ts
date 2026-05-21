import { req } from "@/shared/api/client";
import type {
  PreviewItemsPage,
  PreviewPersistScope,
  PreviewPersistStatus,
  PreviewSession,
} from '@/types';

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
  return req<PreviewItemsPage>(`/preview-sessions/${sessionId}/items?${params}`);
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

export type {
  PreviewItem,
  PreviewItemsPage,
  PreviewPersistScope,
  PreviewPersistStatus,
  PreviewSession,
} from '@/types';
