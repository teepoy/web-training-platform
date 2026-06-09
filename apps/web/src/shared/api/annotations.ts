import {
  createAnnotationApiV1AnnotationsPost,
  updateAnnotationApiV1AnnotationsAnnotationIdPatch,
  deleteAnnotationApiV1AnnotationsAnnotationIdDelete,
} from "@/generated/orval/endpoints/api";
import type { Annotation } from "@/generated/orval/models";

export async function createAnnotation(body: {
  dataset_id: string;
  sample_id: string;
  label: string;
  created_by?: string;
}): Promise<Annotation> {
  return (await
    createAnnotationApiV1AnnotationsPost(
      body as import("@/generated/orval/models/createAnnotationRequest").CreateAnnotationRequest,
    )).data as Annotation;
}

export async function updateAnnotation(
  annotationId: string,
  datasetId: string,
  payload: { label: string },
): Promise<Annotation> {
  return (await
    updateAnnotationApiV1AnnotationsAnnotationIdPatch(annotationId, { dataset_id: datasetId, ...payload })).data as Annotation;
}

export async function deleteAnnotation(annotationId: string, datasetId: string): Promise<void> {
  return (await
    deleteAnnotationApiV1AnnotationsAnnotationIdDelete(annotationId, { dataset_id: datasetId })).data as void;
}
