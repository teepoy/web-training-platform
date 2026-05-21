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

export interface VersionExportResponse {
  uri: string;
  format_id: string;
}

export interface ExportFormat {
  format_id: string;
}
