import { req } from "./client";
import type {
  PredictionJob,
  PredictionResult,
  PredictionEvent,
  RunPredictionRequest,
  PredictSingleRequest,
  ReviewAction,
  AnnotationVersion,
  SaveReviewAnnotationItem,
  SaveReviewAnnotationsResponse,
  PredictionCollection,
  CreatePredictionCollectionRequest,
  SyncPredictionCollectionResponse,
  VersionExportResponse,
} from "./types";

export function runPredictions(
  request: RunPredictionRequest,
): Promise<PredictionJob> {
  return req<PredictionJob>("/predictions/run", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function listPredictionJobs(): Promise<PredictionJob[]> {
  return req<PredictionJob[]>("/prediction-jobs");
}

export function getPredictionJob(id: string): Promise<PredictionJob> {
  return req<PredictionJob>(`/prediction-jobs/${id}`);
}

export function listPredictionJobPredictions(
  id: string,
): Promise<PredictionResult[]> {
  return req<PredictionResult[]>(`/prediction-jobs/${id}/predictions`);
}

export function listPredictionJobEvents(
  id: string,
): Promise<PredictionEvent[]> {
  return req<PredictionEvent[]>(`/prediction-jobs/${id}/events`);
}

export function cancelPredictionJob(
  id: string,
): Promise<{ cancelled: boolean }> {
  return req<{ cancelled: boolean }>(`/prediction-jobs/${id}/cancel`, {
    method: "POST",
  });
}

export function predictSingle(
  request: PredictSingleRequest,
): Promise<PredictionResult> {
  return req<PredictionResult>("/predictions/single", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function listSamplePredictions(
  sampleId: string,
  modelVersion?: string | null,
): Promise<PredictionResult[]> {
  const qs = modelVersion
    ? `?model_version=${encodeURIComponent(modelVersion)}`
    : "";
  return req<PredictionResult[]>(
    `/samples/${sampleId}/predictions${qs}`,
  );
}

export function createPredictionCollection(
  request: CreatePredictionCollectionRequest,
): Promise<PredictionCollection> {
  return req<PredictionCollection>("/prediction-collections", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function listPredictionCollections(
  datasetId: string,
): Promise<PredictionCollection[]> {
  return req<PredictionCollection[]>(
    `/prediction-collections?dataset_id=${encodeURIComponent(datasetId)}`,
  );
}

export function syncPredictionCollection(
  collectionId: string,
  syncTag?: string | null,
): Promise<SyncPredictionCollectionResponse> {
  return req<SyncPredictionCollectionResponse>(
    `/prediction-collections/${collectionId}/sync-label-studio`,
    {
      method: "POST",
      body: JSON.stringify(syncTag ? { sync_tag: syncTag } : {}),
    },
  );
}

export function createReviewAction(
  datasetId: string,
  modelId: string,
  modelVersion?: string | null,
  collectionId?: string | null,
  syncTag?: string | null,
): Promise<ReviewAction> {
  return req<ReviewAction>("/prediction-reviews", {
    method: "POST",
    body: JSON.stringify({
      dataset_id: datasetId,
      model_id: modelId,
      ...(modelVersion ? { model_version: modelVersion } : {}),
      ...(collectionId ? { collection_id: collectionId } : {}),
      ...(syncTag ? { sync_tag: syncTag } : {}),
    }),
  });
}

export function listReviewActions(
  datasetId: string,
): Promise<ReviewAction[]> {
  return req<ReviewAction[]>(
    `/prediction-reviews?dataset_id=${encodeURIComponent(datasetId)}`,
  );
}

export function getReviewAction(actionId: string): Promise<ReviewAction> {
  return req<ReviewAction>(`/prediction-reviews/${actionId}`);
}

export function deleteReviewAction(actionId: string): Promise<void> {
  return req<void>(`/prediction-reviews/${actionId}`, { method: "DELETE" });
}

export function saveReviewAnnotations(
  actionId: string,
  items: SaveReviewAnnotationItem[],
): Promise<SaveReviewAnnotationsResponse> {
  return req<SaveReviewAnnotationsResponse>(
    `/prediction-reviews/${actionId}/annotations`,
    {
      method: "POST",
      body: JSON.stringify({ items }),
    },
  );
}

export function listAnnotationVersions(
  actionId: string,
): Promise<AnnotationVersion[]> {
  return req<AnnotationVersion[]>(
    `/prediction-reviews/${actionId}/annotation-versions`,
  );
}

export function previewReviewExport(
  actionId: string,
  formatId?: string,
): Promise<Record<string, unknown>> {
  const params = new URLSearchParams();
  if (formatId) params.set("format_id", formatId);
  const qs = params.toString() ? `?${params.toString()}` : "";
  return req<Record<string, unknown>>(
    `/prediction-reviews/${actionId}/export${qs}`,
  );
}

export function persistReviewExport(
  actionId: string,
  formatId?: string,
): Promise<VersionExportResponse> {
  return req<VersionExportResponse>(
    `/prediction-reviews/${actionId}/export/persist`,
    {
      method: "POST",
      body: JSON.stringify({
        format_id: formatId ?? "annotation-version-full-context-v1",
      }),
    },
  );
}
