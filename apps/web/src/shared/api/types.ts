// Shared types used across API domain modules.
// Mirrors types from apps/web/src/api.ts and apps/web/src/types.ts.

export interface Dataset {
  id: string;
  name: string;
  dataset_type: DatasetType;
  task_spec: {
    task_type: TaskType;
    label_space: string[];
    metadata_schema?: Record<string, { type: string; description: string }>;
  };
  created_at: string;
  ls_project_id?: string | null;
  ls_project_url?: string | null;
  org_id?: string;
  org_name?: string;
  is_public?: boolean;
  storage_mode: DatasetStorageMode;
  capabilities?: Record<string, boolean>;
}

export interface Sample {
  id: string;
  dataset_id: string;
  image_uris: string[];
  metadata: Record<string, unknown>;
  ls_task_id?: number | null;
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

export interface Annotation {
  id: string;
  sample_id: string;
  label: string;
  created_by: string;
  created_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
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

export interface DatasetAnnotationStats {
  total_samples: number;
  annotated_samples: number;
  unlabeled_samples: number;
  label_counts: Record<string, number>;
}

export interface SparseShardSummary {
  shard_index: number;
  row_count: number;
  format: string;
  byte_size: number;
}

export interface SparseManifestSummary {
  shard_count: number;
  total_rows: number;
  schema_columns: Array<{ name: string; type: string }>;
  created_at: string;
}

export interface SparseSummaryResponse {
  dataset_id: string;
  name: string;
  dataset_type: string;
  storage_mode: string;
  manifest: SparseManifestSummary;
  shards: SparseShardSummary[];
  sample_rows: Array<Record<string, unknown>>;
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

export interface SyncResult {
  synced_count: number;
  skipped_count?: number;
  errors: string[];
}

export interface TrainingPreset {
  id: string;
  name: string;
  version?: string;
  description?: string;
  tags?: string[];
  deprecated?: boolean;
  trainable?: boolean;
  model: { framework: string; base_model: string; source?: string | null; checkpoint?: string | null };
  train: { process: string; dataloader?: { ref: string } | null; hyperparams?: Record<string, unknown> };
  predict: { targets: Record<string, { process: string; label_space?: string[] | null; threshold?: number | null }> };
  test?: Record<string, unknown> | null;
  convert?: Record<string, unknown> | null;
  runtime: { gpu?: boolean; min_vram_gb?: number | null; env?: Record<string, string>; queue?: string | null };
  compatibility?: { dataset_types: string[]; task_types: string[]; prediction_targets: string[] };
  model_spec?: { architecture: string; num_classes: number } | { framework: string; base_model: string };
  omegaconf_yaml?: string;
  dataloader_ref?: string;
  org_id?: string | null;
}

export interface TrainingJob {
  id: string;
  dataset_id: string;
  preset_id: string;
  status: JobStatus;
  created_by: string;
  created_at: string;
  updated_at: string;
  artifact_refs: Array<{ id: string; uri: string; kind: string; metadata: Record<string, unknown> }>;
  org_id?: string;
  org_name?: string;
  is_public?: boolean;
}

export interface ModelUploadTemplate {
  id: string;
  name: string;
  dataset_types: string[];
  task_types: string[];
  profiles: Array<{ id: string; name: string; model_spec: Record<string, string>; default_prediction_targets: string[] }>;
  label_space_mode: "required" | "forbidden";
  requires_embedding_metadata: boolean;
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

export interface UploadModelMetadata {
  name: string;
  format: string;
  job_id: string;
  template_id: string;
  profile_id: string;
  model_spec: { framework: string; architecture: string; base_model: string };
  compatibility: {
    dataset_types: string[];
    task_types: string[];
    prediction_targets: string[];
    label_space: string[];
    embedding_dimension?: number | null;
    normalized_output?: boolean | null;
  };
}

export interface UploadResponse {
  uri: string;
  sample_id: string;
  index: number;
}

export interface DashboardResponse {
  work_pool: {
    name: string;
    type: string;
    is_paused: boolean;
    concurrency_limit: number | null;
    slots_used: number;
    status: string;
  } | null;
  job_queue: {
    queued: number;
    running: number;
    completed: number;
    failed: number;
    cancelled: number;
  };
  recent_jobs: Array<{
    id: string;
    dataset_id: string;
    preset_id: string;
    status: string;
    created_by: string;
    created_at: string;
    updated_at: string;
  }>;
  services: Array<{
    name: string;
    kind: string;
    status: string;
    detail: string;
    latency_ms: number | null;
    endpoint: string | null;
  }>;
  prefect_connected: boolean;
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

export interface CancelJobResponse {
  cancelled: boolean;
}

export interface MarkLeftResponse {
  marked: boolean;
}

export interface ExtractFeaturesResponse {
  id: string;
  status: string;
  summary: Record<string, unknown>;
}

export interface SimilarityResponse {
  sample_id: string;
  neighbors: Array<{ sample_id: string; score: number }>;
}

export interface SelectionMetricsResponse {
  uniqueness: Record<string, number>;
  representativeness: Record<string, number>;
}

export interface UncoveredHintsResponse {
  dataset_id?: string;
  clusters: Array<{ cluster_id: string; size: number; hint: string }>;
}

export interface DatasetExport {
  dataset: Dataset;
  samples: Sample[];
  annotations: Annotation[];
}

export interface PersistExportResponse {
  uri: string;
}

export interface ExportFormat {
  format_id: string;
}

export interface ExportFormatItem {
  format_id: string;
}

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

export type OrgRole = "admin" | "member";

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
  user: User;
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

export interface OAuthCallbackResponse {
  action: "login" | "register";
  access_token?: string | null;
  user?: User | null;
  state_token?: string | null;
  email?: string | null;
  name?: string | null;
  provider?: string | null;
  provider_id?: string | null;
}

export interface OAuthProviderInfo {
  id: string;
  display_name: string;
  enabled: boolean;
}

export interface OAuthRegisterRequest {
  state_token: string;
  name: string;
}

// Prediction types
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

// Agent / Display Surface types
export interface AgentPanelDescriptor {
  id: string;
  component: string;
  title: string;
  order: number;
  collapsed: boolean;
  size: "compact" | "normal" | "large";
  data: Record<string, unknown> | null;
  data_source:
    | { kind: "api"; endpoint: string; params: Record<string, string>; refresh_interval: number }
    | { kind: "context"; key: string; path: string | null }
    | null;
  config: Record<string, unknown>;
  ephemeral: boolean;
  ttl: number | null;
}

export interface SurfaceStateDocument {
  version: number;
  surface_id: string;
  panels: AgentPanelDescriptor[];
  layout: { width: number; position: "right" | "left" };
  exported_at: string | null;
  metadata: Record<string, unknown>;
}

export interface WaferPoint {
  id: string;
  x: number;
  y: number;
  value?: number;
}

export interface WaferPointsQueryResponse {
  points: WaferPoint[];
  total: number;
}

export interface FetchSampleSliceOptions {
  offset?: number;
  limit?: number;
  label?: string | null;
  orderBy?: string;
  sampleIds?: string[] | null;
}

export interface UpdateAnnotationPayload {
  label: string;
}

export interface GlobalChatRequest {
  message: string;
  context: {
    page: string;
    dataset_id?: string | null;
    job_id?: string | null;
    schedule_id?: string | null;
    extra?: Record<string, unknown>;
  };
  session_id?: string | null;
}

// Request body interfaces (mirrors apps/web/src/api.ts)
export interface CreateDatasetBody {
  name: string;
  dataset_type: DatasetType;
  task_spec?: {
    task_type: TaskType;
    label_space: string[];
    metadata_schema?: Record<string, { type: string; description: string }>;
  };
  storage_mode?: DatasetStorageMode;
}

export interface CreateSampleBody {
  image_uris: string[];
  metadata?: Record<string, unknown>;
}

export interface CreateAnnotationBody {
  sample_id: string;
  label: string;
  created_by?: string;
}

export interface CreateScheduleBody {
  name: string;
  flow_name: string;
  cron: string;
  parameters?: Record<string, unknown>;
  description?: string;
}

export interface UpdateScheduleBody {
  name?: string;
  cron?: string;
  parameters?: Record<string, unknown>;
  description?: string;
  is_schedule_active?: boolean;
}

// ---------------------------------------------------------------------------
// Type aliases
// ---------------------------------------------------------------------------
export type TaskType = "classification" | "vqa" | "detection";
export type DatasetType = "image_classification" | "image_vqa" | "image_detection";
export type DatasetStorageMode = "db_full" | "file_shard_sparse";
export type ModelFramework = "pytorch" | "dspy";
export type JobStatus = "queued" | "running" | "completed" | "failed" | "cancelled";
export type ScheduleStatus = "active" | "paused";
export type ModelFormat = "pytorch" | "onnx" | "safetensors" | "keras";

// ---------------------------------------------------------------------------
// Task spec
// ---------------------------------------------------------------------------
export interface TaskSpec {
  task_type: TaskType;
  label_space: string[];
  metadata_schema?: Record<string, { type: string; description: string }>;
}

// ---------------------------------------------------------------------------
// Sparse prediction types
// ---------------------------------------------------------------------------
export interface SparsePredictionResult {
  locator: { shard_index: number; row_index: number };
  predicted_label: string;
  confidence?: number | null;
  error?: string | null;
}

export interface SparsePredictionShard {
  shard_uri: string;
  shard_index: number;
  model_id: string;
  model_version?: string | null;
  results: SparsePredictionResult[];
  created_at: string;
}

export interface SparsePredictionJobResult {
  job_id: string;
  dataset_id: string;
  model_id: string;
  model_version?: string | null;
  shards: SparsePredictionShard[];
  total_processed: number;
  total_successful: number;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Model / Preset detail types
// ---------------------------------------------------------------------------
export interface ModelSpec {
  architecture: string;
  num_classes: number;
}

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

export interface ArtifactRef {
  id: string;
  uri: string;
  kind: string;
  metadata: Record<string, unknown>;
}

export interface SampleFeature {
  sample_id: string;
  embedding: number[];
}

// ---------------------------------------------------------------------------
// Common
// ---------------------------------------------------------------------------
export interface ApiError {
  detail: string;
  status: number;
}

export interface HealthStatus {
  status: string;
  auth_enabled: boolean;
}

// ---------------------------------------------------------------------------
// Dashboard sub-types
// ---------------------------------------------------------------------------
export interface WorkPoolStatus {
  name: string;
  type: string;
  is_paused: boolean;
  concurrency_limit: number | null;
  slots_used: number;
  status: string;
}

export interface JobQueueStats {
  queued: number;
  running: number;
  completed: number;
  failed: number;
  cancelled: number;
}

export interface RecentJobSummary {
  id: string;
  dataset_id: string;
  preset_id: string;
  status: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface ServiceStatus {
  name: string;
  kind: string;
  status: string;
  detail: string;
  latency_ms: number | null;
  endpoint: string | null;
}

// ---------------------------------------------------------------------------
// Model upload types
// ---------------------------------------------------------------------------
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

// ---------------------------------------------------------------------------
// Task tracker detail types
// ---------------------------------------------------------------------------
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
  expected_start_at: string | null;
  started_at: string | null;
  ended_at: string | null;
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

// ---------------------------------------------------------------------------
// Agent context
// ---------------------------------------------------------------------------
export interface AgentContext {
  page: string;
  dataset_id?: string | null;
  job_id?: string | null;
  schedule_id?: string | null;
  extra?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Sensors
// ---------------------------------------------------------------------------
export interface SensorDefinition {
  id: string;
  name: string;
  description: string;
  cron: string;
  filter_schema: Record<string, unknown>;
  available_triggers: string[];
}

export interface SensorSubscription {
  id: string;
  sensor_id: string;
  workflow_type: string;
  filter_config: Record<string, unknown>;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateSubscriptionBody {
  workflow_type: string;
  filter_config?: Record<string, unknown>;
  enabled?: boolean;
}

export interface UpdateSubscriptionBody {
  filter_config?: Record<string, unknown>;
  enabled?: boolean;
}
