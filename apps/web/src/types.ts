export type TaskType = "classification" | "vqa";
export type DatasetType = "image_classification" | "image_vqa";
export type ModelFramework = "pytorch" | "dspy";
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
  ls_project_url?: string | null;
  org_id?: string;
  org_name?: string;
  is_public?: boolean;
}

export interface Sample {
  id: string;
  dataset_id: string;
  image_uris: string[];
  metadata: Record<string, unknown>;
  ls_task_id?: number | null;
}

export interface BulkCreateSampleItem {
  image_uris: string[];
  metadata: Record<string, unknown>;
  label?: string | null;
}

export interface BulkCreateSampleResponse {
  dataset_id: string;
  imported: number;
  failed: number;
  sample_ids: string[];
  ls_task_ids: number[];
  errors: string[];
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

export interface SampleWithLabels {
  id: string;
  dataset_id: string;
  image_uris: string[];
  metadata: Record<string, unknown>;
  ls_task_id?: number | null;
  latest_annotation: LatestAnnotation | null;
}

export interface ModelSpec {
  architecture: string;
  num_classes: number;
}

// ---------------------------------------------------------------------------
// File-backed preset (new shape from preset registry)
// ---------------------------------------------------------------------------

export interface PresetModelSource {
  framework: string;
  base_model: string;
  source?: string | null;
  checkpoint?: string | null;
}

export interface PresetTrainConfig {
  process: string;
  dataloader?: { ref: string } | null;
  hyperparams?: Record<string, unknown>;
}

export interface PresetPredictTarget {
  process: string;
  label_space?: string[] | null;
  threshold?: number | null;
}

export interface PresetPredictConfig {
  targets: Record<string, PresetPredictTarget>;
}

export interface PresetRuntimeConfig {
  gpu?: boolean;
  min_vram_gb?: number | null;
  env?: Record<string, string>;
  queue?: string | null;
}

export interface PresetCompatibility {
  dataset_types: string[];
  task_types: string[];
  prediction_targets: string[];
}

export interface TrainingPreset {
  id: string;
  name: string;
  version?: string;
  description?: string;
  tags?: string[];
  deprecated?: boolean;
  trainable?: boolean;
  model: PresetModelSource;
  train: PresetTrainConfig;
  predict: PresetPredictConfig;
  test?: Record<string, unknown> | null;
  convert?: Record<string, unknown> | null;
  runtime: PresetRuntimeConfig;
  compatibility?: PresetCompatibility;
  // Legacy compat fields
  model_spec?: ModelSpec | { framework: string; base_model: string };
  omegaconf_yaml?: string;
  dataloader_ref?: string;
  org_id?: string | null;
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
  org_id?: string;
  org_name?: string;
  is_public?: boolean;
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

export interface ServiceStatus {
  name: string
  kind: string
  status: string
  detail: string
  latency_ms: number | null
  endpoint: string | null
}

export interface DashboardResponse {
  work_pool: WorkPoolStatus | null
  job_queue: JobQueueStats
  recent_jobs: RecentJobSummary[]
  services: ServiceStatus[]
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

// ---------------------------------------------------------------------------
// Model artifacts
// ---------------------------------------------------------------------------

export type ModelFormat = "pytorch" | "onnx" | "safetensors" | "keras";

export interface ModelCompatibility {
  dataset_types: string[];
  task_types: string[];
  prediction_targets: string[];
  label_space: string[];
  embedding_dimension?: number | null;
  normalized_output?: boolean | null;
}

export interface UploadedModelSpec {
  framework: string;
  architecture: string;
  base_model: string;
}

export interface ModelUploadProfile {
  id: string;
  name: string;
  model_spec: Record<string, string>;
  default_prediction_targets: string[];
}

export interface ModelUploadTemplate {
  id: string;
  name: string;
  dataset_types: string[];
  task_types: string[];
  profiles: ModelUploadProfile[];
  label_space_mode: "required" | "forbidden";
  requires_embedding_metadata: boolean;
}

export interface UploadModelMetadata {
  name: string;
  format: ModelFormat;
  job_id: string;
  template_id: string;
  profile_id: string;
  model_spec: UploadedModelSpec;
  compatibility: ModelCompatibility;
}

export interface Model {
  id: string;
  uri: string;
  kind: string;
  name: string | null;
  file_size: number | null;
  file_hash: string | null;
  format: string | null;
  created_at: string | null;
  metadata: Record<string, unknown>;
  job_id: string;
  dataset_id: string;
  dataset_name: string;
  preset_name: string;
}

// ---------------------------------------------------------------------------
// Predictions
// ---------------------------------------------------------------------------

export interface PredictionResult {
  sample_id: string;
  ls_task_id: number | null;
  predicted_label: string;
  confidence: number | null;
  ls_prediction_id: number | null;
  error: string | null;
}

export interface BatchPredictionResult {
  model_id: string;
  dataset_id: string;
  total_samples: number;
  successful: number;
  failed: number;
  predictions: PredictionResult[];
  started_at: string;
  completed_at: string;
  model_version: string | null;
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

// ---------------------------------------------------------------------------
// Prediction Review
// ---------------------------------------------------------------------------

export interface ReviewAction {
  id: string;
  dataset_id: string;
  model_id: string;
  model_version: string | null;
  created_by: string;
  created_at: string;
}

export interface AnnotationVersion {
  id: string;
  review_action_id: string;
  annotation_id: string;
  source_prediction_id: number | null;
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
  source_prediction_id: number | null;
}

export interface SaveReviewAnnotationsResponse {
  review_action_id: string;
  created_count: number;
  annotation_versions: AnnotationVersion[];
}

export interface ExportFormat {
  format_id: string;
}

export interface VersionExportResponse {
  uri: string;
  format_id: string;
}

export interface TaskTrackerCheckResult {
  key: string;
  label: string;
  status: string;
  message: string;
  value: string | null;
}

export interface TaskTrackerScorecard {
  errors: number;
  warnings: number;
  checks: TaskTrackerCheckResult[];
}

export interface TaskTrackerNode {
  key: string;
  label: string;
  status: string;
  detail: string;
}

export interface TaskTrackerStage {
  key: string;
  label: string;
  status: string;
  summary: string;
  nodes: TaskTrackerNode[];
}

export interface TaskTrackerSummaryMetrics {
  total: number | null;
  processed: number | null;
  successful: number | null;
  failed: number | null;
  skipped: number | null;
  rate_hint: string | null;
}

export interface TaskTrackerDeepLinks {
  prefect_run_url: string | null;
  prefect_deployment_url: string | null;
  platform_job_url: string | null;
}

export interface TaskTrackerRawPayload {
  platform_job: Record<string, unknown>;
  flow_run: Record<string, unknown> | null;
  deployment: Record<string, unknown> | null;
  work_queue: Record<string, unknown> | null;
  work_pool: Record<string, unknown> | null;
  logs: Record<string, unknown>[];
}

export interface TaskTrackerDerived {
  task_kind: string;
  execution_kind: string;
  display_status: string;
  prefect_state: string | null;
  stage: string;
  active_node: string | null;
  capacity_status: string;
  queue_priority: number | null;
  queue_priority_label: string;
  queue_depth_ahead: number | null;
  pool_concurrency_limit: number | null;
  pool_slots_used: number | null;
  stages: TaskTrackerStage[];
  scorecard: TaskTrackerScorecard;
  summary_metrics: TaskTrackerSummaryMetrics;
  artifacts: Record<string, unknown>[];
  dynamic_console_lines: string[];
  deep_links: TaskTrackerDeepLinks;
}

export interface TaskTrackerSummary {
  id: string;
  task_kind: string;
  execution_kind: string;
  display_name: string;
  display_status: string;
  stage: string;
  dataset_id: string;
  model_id: string | null;
  preset_id: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  prefect_state: string | null;
  work_pool_name: string | null;
  work_queue_name: string | null;
  queue_priority: number | null;
  queue_priority_label: string;
  queue_depth_ahead: number | null;
  capacity_status: string;
  pool_concurrency_limit: number | null;
  pool_slots_used: number | null;
}

export interface TaskTrackerDetail {
  id: string;
  task_kind: string;
  meta: Record<string, unknown>;
  raw: TaskTrackerRawPayload;
  derived: TaskTrackerDerived;
}
