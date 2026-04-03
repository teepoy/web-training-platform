export type TaskType = "classification";
export type DatasetType = "image_classification";
export type ModelFramework = "pytorch";
export type ResultType = "class_prediction";
export type JobStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export interface TaskSpec {
  task_type: TaskType;
  label_space: string[];
}

export interface Dataset {
  id: string;
  name: string;
  dataset_type: DatasetType;
  task_spec: TaskSpec;
  created_at: string;
}

export interface Sample {
  id: string;
  dataset_id: string;
  image_uris: string[];
  metadata: Record<string, unknown>;
}

export interface Annotation {
  id: string;
  sample_id: string;
  label: string;
  created_by: string;
  created_at: string;
}

export interface ModelSpec {
  architecture: string;
  num_classes: number;
}

export interface TrainingPreset {
  id: string;
  name: string;
  model_spec: ModelSpec;
  omegaconf_yaml: string;
  dataloader_ref: string;
  created_at?: string;
}

export interface TrainingEvent {
  job_id: string;
  ts: string;
  level: string;
  message: string;
  payload: Record<string, unknown>;
}

export interface ArtifactRef {
  id: string;
  uri: string;
  kind: string;
  metadata: Record<string, unknown>;
}

export interface TrainingJob {
  id: string;
  dataset_id: string;
  preset_id: string;
  status: JobStatus;
  created_by: string;
  created_at: string;
  updated_at: string;
  artifact_refs: ArtifactRef[];
}

export interface PredictionResult {
  id: string;
  result_type: ResultType;
  sample_id: string;
  predicted_label: string;
  score: number;
  model_artifact_id: string;
}

export interface PredictionEdit {
  id: string;
  result_id: string;
  corrected_label: string;
  edited_by: string;
  edited_at: string;
}

export interface SampleFeature {
  sample_id: string;
  embedding: number[];
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
}

export interface ApiError {
  detail: string;
  status: number;
}

export interface UploadResponse {
  uri: string;
  sample_id: string;
  index: number;
}

export interface UpdateAnnotationPayload {
  label: string;
}
