import { req } from "./client";
import type {
  Annotation,
  UpdateAnnotationPayload,
} from "./types";

export function createAnnotation(body: {
  sample_id: string;
  label: string;
  created_by?: string;
}): Promise<Annotation> {
  return req<Annotation>("/annotations", {
    method: "POST",
    body: JSON.stringify({
      sample_id: body.sample_id,
      label: body.label,
      ...(body.created_by !== undefined
        ? { created_by: body.created_by }
        : {}),
    }),
  });
}

export function updateAnnotation(
  annotationId: string,
  payload: UpdateAnnotationPayload,
): Promise<Annotation> {
  return req<Annotation>(`/annotations/${annotationId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteAnnotation(annotationId: string): Promise<void> {
  return req<void>(`/annotations/${annotationId}`, { method: "DELETE" });
}
