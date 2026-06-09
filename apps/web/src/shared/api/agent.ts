import { req } from "./client";
import type { SurfaceStateDocument } from "./types";
import type { AgentPanelDescriptor } from "@/generated/orval/models";

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
  return req(
    `/sessions/${sessionId}/surfaces/${surfaceId}/panels/${panelId}`,
    {
      method: "DELETE",
    },
  );
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
