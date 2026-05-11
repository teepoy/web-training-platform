import { req } from "../client/apiClient";

export interface PredictionResult {
  id: string | null;
  sample_id: string;
  predicted_label: string;
  confidence: number | null;
  model_id: string | null;
  target: string | null;
  model_version: string | null;
  job_id: string | null;
  created_at: string | null;
  error: string | null;
}

export interface PredictionJob {
  id: string;
  dataset_id: string;
  model_id: string;
  status: string;
  created_by: string;
  target: string;
  model_version: string | null;
  created_at: string;
  updated_at: string;
  external_job_id: string | null;
  sample_ids: string[] | null;
  summary: Record<string, unknown>;
}

export interface PredictionEvent {
  job_id: string;
  ts: string;
  level: string;
  message: string;
  payload: Record<string, unknown>;
}

export interface RunPredictionRequest {
  model_id: string;
  dataset_id: string;
  sample_ids?: string[] | null;
  model_version?: string | null;
  target?: string;
  prompt?: string | null;
}

export interface PredictSingleRequest {
  model_id: string;
  sample_id: string;
  model_version?: string | null;
  target?: string;
  prompt?: string | null;
}

export interface ReviewAction {
  id: string;
  dataset_id: string;
  model_id: string;
  model_version: string | null;
  collection_id: string | null;
  sync_tag: string | null;
  created_by: string;
  created_at: string;
}

export interface AnnotationVersion {
  id: string;
  review_action_id: string;
  annotation_id: string;
  prediction_id: string | null;
  predicted_label: string;
  final_label: string;
  confidence: number | null;
  created_at: string;
}

export interface SaveReviewAnnotationItem {
  sample_id: string;
  predicted_label: string;
  final_label: string;
  confidence: number | null;
  prediction_id: string | null;
}

export interface SaveReviewAnnotationsResponse {
  review_action_id: string;
  created_count: number;
  annotation_versions: AnnotationVersion[];
}

export interface PredictionCollection {
  id: string;
  name: string;
  dataset_id: string;
  model_id: string;
  model_version: string | null;
  target: string;
  source_job_id: string | null;
  sync_tag: string | null;
  created_by: string;
  created_at: string;
  prediction_ids: string[];
}

export interface CreatePredictionCollectionRequest {
  name: string;
  dataset_id: string;
  model_id: string;
  prediction_ids: string[];
  model_version?: string | null;
  target?: string;
  source_job_id?: string | null;
}

export interface SyncPredictionCollectionResponse {
  collection_id: string;
  sync_tag: string;
  synced_count: number;
  failed_count: number;
  errors: string[];
}

export interface ExportFormat {
  format_id: string;
}

export interface VersionExportResponse {
  uri: string;
  format_id: string;
}

export function runPredictions(request: RunPredictionRequest): Promise<PredictionJob> {
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

export function listPredictionJobPredictions(id: string): Promise<PredictionResult[]> {
  return req<PredictionResult[]>(`/prediction-jobs/${id}/predictions`);
}

export function listPredictionJobEvents(id: string): Promise<PredictionEvent[]> {
  return req<PredictionEvent[]>(`/prediction-jobs/${id}/events`);
}

export function cancelPredictionJob(id: string): Promise<{ cancelled: boolean }> {
  return req<{ cancelled: boolean }>(`/prediction-jobs/${id}/cancel`, {
    method: "POST",
  });
}

export function predictSingle(request: PredictSingleRequest): Promise<PredictionResult> {
  return req<PredictionResult>("/predictions/single", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function createReviewAction(params: {
  dataset_id: string;
  model_id: string;
  model_version?: string | null;
  collection_id?: string | null;
  sync_tag?: string | null;
}): Promise<ReviewAction> {
  return req<ReviewAction>("/prediction-reviews", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export function listReviewActions(datasetId: string): Promise<ReviewAction[]> {
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

export function listAnnotationVersions(actionId: string): Promise<AnnotationVersion[]> {
  return req<AnnotationVersion[]>(
    `/prediction-reviews/${actionId}/annotation-versions`,
  );
}

export function createPredictionCollection(params: CreatePredictionCollectionRequest): Promise<PredictionCollection> {
  return req<PredictionCollection>("/prediction-collections", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export function listPredictionCollections(datasetId: string): Promise<PredictionCollection[]> {
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
