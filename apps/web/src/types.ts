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
  ls_project_id?: string | null;
}

export interface Sample {
  id: string;
  dataset_id: string;
  image_uris: string[];
  metadata: Record<string, unknown>;
  ls_task_id?: number | null;
}

export interface Annotation {
  id: string;
  sample_id: string;
  label: string;
  created_by: string;
  created_at: string;
}

export interface LatestAnnotation {
  id: string;
  label: string;
  created_by: string;
  created_at: string;
}

export interface LatestPrediction {
  id: string;
  predicted_label: string;
  score: number;
  model_artifact_id: string;
}

export interface SampleWithLabels {
  id: string;
  dataset_id: string;
  image_uris: string[];
  metadata: Record<string, unknown>;
  ls_task_id?: number | null;
  latest_annotation: LatestAnnotation | null;
  latest_prediction: LatestPrediction | null;
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

export type ScheduleStatus = "active" | "paused";

export interface Schedule {
  id: string;
  name: string;
  flow_name: string;
  cron: string | null;
  parameters: Record<string, unknown>;
  description: string;
  is_schedule_active: boolean;
  created: string | null;
  updated: string | null;
  prefect_deployment_id: string;
}

export interface ScheduleRun {
  id: string;
  name: string;
  deployment_id: string | null;
  flow_name: string | null;
  state_type: string | null;
  state_name: string | null;
  start_time: string | null;
  end_time: string | null;
  total_run_time: number | null;
  parameters: Record<string, unknown>;
}

export interface RunLog {
  id: string | null;
  flow_run_id: string | null;
  level: number;
  timestamp: string;
  message: string;
}

export interface SyncResult {
  synced_count: number;
  skipped_count?: number;
  errors: string[];
}

export interface LinkLsRequest {
  ls_project_id: number;
}

export interface BulkAnnotationItem {
  sample_id: string;
  label: string;
  annotator: string;
}

export interface BulkAnnotationRequest {
  annotations: BulkAnnotationItem[];
}

export interface BulkAnnotationResponse {
  created: number;
}

export interface WorkPoolStatus {
  name: string
  type: string
  is_paused: boolean
  concurrency_limit: number | null
  slots_used: number
  status: string
}

export interface JobQueueStats {
  queued: number
  running: number
  completed: number
  failed: number
  cancelled: number
}

export interface RecentJobSummary {
  id: string
  dataset_id: string
  preset_id: string
  status: string
  created_by: string
  created_at: string
  updated_at: string
}

export interface DashboardResponse {
  work_pool: WorkPoolStatus | null
  job_queue: JobQueueStats
  recent_jobs: RecentJobSummary[]
  prefect_connected: boolean
}

export type OrgRole = "admin" | "member";

export interface User {
  id: string;
  email: string;
  name: string;
  is_superadmin: boolean;
  is_active: boolean;
  created_at: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  created_at: string;
}

export interface OrgMembership {
  id: string;
  user_id: string;
  org_id: string;
  role: OrgRole;
  created_at: string;
}

export interface UserWithOrgs extends User {
  organizations: OrgMembership[];
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface PersonalAccessToken {
  id: string;
  user_id: string;
  name: string;
  token_prefix: string;
  created_at: string;
  last_used_at: string | null;
}

export interface PersonalAccessTokenCreated extends PersonalAccessToken {
  token: string;
}

export interface OrgMember {
  user_id: string;
  org_id: string;
  role: OrgRole;
  user: User;
}
