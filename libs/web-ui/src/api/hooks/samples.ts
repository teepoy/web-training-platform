import { useQuery, useMutation } from "@tanstack/vue-query";
import { computed } from "vue";
import {
  getSample,
  listAnnotationsForSample,
  uploadSampleImage,
} from "../samples";
import {
  createAnnotation,
  updateAnnotation,
  deleteAnnotation,
} from "../annotations";
import { getSimilarity } from "../datasets";

export const sampleKeys = {
  all: ["samples"] as const,
  list: (datasetId: string, filters?: Record<string, unknown>) =>
    ["samples", "list", datasetId, filters ?? {}] as const,
  detail: (sampleId: string) => ["samples", "detail", sampleId] as const,
  annotations: (sampleId: string) =>
    ["samples", "annotations", sampleId] as const,
  similarity: (datasetId: string, sampleId: string, k?: number) =>
    ["samples", "similarity", datasetId, sampleId, k ?? 5] as const,
};

export function useSampleQuery(sampleId: () => string | null) {
  return useQuery({
    queryKey: computed(() => {
      const id = sampleId();
      return id ? sampleKeys.detail(id) : sampleKeys.all;
    }),
    queryFn: ({ queryKey }) => {
      const id = queryKey[2] as string;
      return getSample(id);
    },
    enabled: computed(() => !!sampleId()),
  });
}

export function useSampleAnnotationsQuery(sampleId: () => string | null) {
  return useQuery({
    queryKey: computed(() => {
      const id = sampleId();
      return id ? sampleKeys.annotations(id) : sampleKeys.all;
    }),
    queryFn: ({ queryKey }) => {
      const id = queryKey[2] as string;
      return listAnnotationsForSample(id);
    },
    enabled: computed(() => !!sampleId()),
  });
}

export function useUpdateAnnotationMutation() {
  return useMutation({
    mutationFn: ({
      annotationId,
      label,
    }: {
      annotationId: string;
      label: string;
    }) => updateAnnotation(annotationId, { label }),
  });
}

export function useDeleteAnnotationMutation() {
  return useMutation({
    mutationFn: (annotationId: string) => deleteAnnotation(annotationId),
  });
}

export function useCreateAnnotationMutation() {
  return useMutation({
    mutationFn: (body: {
      sample_id: string;
      label: string;
      created_by?: string;
    }) => createAnnotation(body),
  });
}

export function useUploadSampleImageMutation() {
  return useMutation({
    mutationFn: ({
      sampleId,
      file,
    }: {
      sampleId: string;
      file: File;
    }) => uploadSampleImage(sampleId, file),
  });
}

export function useSimilarityQuery(
  datasetId: () => string,
  sampleId: () => string | null,
  k?: number,
) {
  return useQuery({
    queryKey: computed(() => {
      const sid = sampleId();
      const did = datasetId();
      return sid ? sampleKeys.similarity(did, sid, k) : sampleKeys.all;
    }),
    queryFn: ({ queryKey }) => {
      const did = queryKey[2] as string;
      const sid = queryKey[3] as string;
      const kk = queryKey[4] as number;
      return getSimilarity(did, sid, kk);
    },
    enabled: computed(() => !!sampleId() && !!datasetId()),
  });
}
