export type TaskType = "classification" | "vqa" | "detection";
export type DatasetType = "image_classification" | "image_vqa" | "image_detection";
export type ModelFramework = "pytorch" | "dspy";
export type JobStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export interface TaskSpec {
  task_type: TaskType;
  label_space: string[];
  metadata_schema?: Record<string, { type: string; description: string }>;
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
  embed_config?: Record<string, unknown> | null;
  storage_mode?: "db_full" | "file_shard_sparse";
}

export interface Sample {
  id: string;
  dataset_id: string;
  image_uris: string[];
  metadata: Record<string, unknown>;
  ls_task_id?: number | null;
  created_at?: string | null;
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

export interface TrainingEvent {
  job_id: string;
  ts: string;
  level: string;
  message: string;
  payload: Record<string, unknown>;
}

export interface ArtifactRef {
  id: string | null;
  uri: string;
  kind: string;
  metadata: Record<string, unknown>;
  name?: string | null;
  file_size?: number | null;
  file_hash?: string | null;
  format?: string | null;
  created_at?: string | null;
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
  external_job_id?: string | null;
  org_id?: string;
  org_name?: string;
  is_public?: boolean;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
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

export interface DashboardResponse {
  work_pool: WorkPoolStatus | null;
  job_queue: JobQueueStats;
  recent_jobs: RecentJobSummary[];
  services: ServiceStatus[];
  prefect_connected: boolean;
}

export interface DatasetAnnotationStats {
  total_samples: number;
  annotated_samples: number;
  unlabeled_samples: number;
  label_counts: Record<string, number>;
}

export type OrgRole = "admin" | "member";

export interface User {
  id: string;
  email: string;
  name: string;
  is_superadmin: boolean;
  created_at: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  created_at: string;
}

export interface OrgMembership {
  org_id: string;
  org_name: string;
  org_slug: string;
  role: OrgRole;
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
  name: string;
  token_prefix: string;
  created_at: string;
  last_used_at: string | null;
}

export interface PersonalAccessTokenCreated {
  id: string;
  name: string;
  token: string;
  created_at: string;
}

export interface OrgMember {
  id: string;
  user_id: string;
  user_email: string;
  user_name: string;
  role: OrgRole;
  created_at: string;
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
  label_space_mode: string;
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

export type RunPredictionRequest = Record<string, unknown>;
export type PredictSingleRequest = Record<string, unknown>;

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

export interface SaveReviewAnnotationsResponse {
  review_action_id: string;
  created_count: number;
  annotation_versions: AnnotationVersion[];
}

export interface ExportFormat {
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

export interface AgentPanelDescriptor {
  id: string;
  component: string;
  title: string;
  order: number;
  collapsed: boolean;
  size: "compact" | "normal" | "large";
  data: Record<string, unknown> | null;
  data_source: AgentDataSourceApi | AgentDataSourceContext | null;
  config: Record<string, unknown>;
  ephemeral: boolean;
  ttl: number | null;
}

export interface AgentDataSourceApi {
  kind: "api";
  endpoint: string;
  params: Record<string, string>;
  refresh_interval: number;
}

export interface AgentDataSourceContext {
  kind: "context";
  key: string;
  path: string | null;
}

export interface SurfaceLayout {
  width: number;
  position: "right" | "left";
}

export interface SurfaceStateDocument {
  version: number;
  surface_id: string;
  panels: AgentPanelDescriptor[];
  layout: SurfaceLayout;
  exported_at: string | null;
  metadata: Record<string, unknown>;
}

export interface AgentContext {
  page: string;
  dataset_id?: string | null;
  job_id?: string | null;
  schedule_id?: string | null;
  extra?: Record<string, unknown>;
}

export interface GlobalChatRequest {
  message: string;
  context: AgentContext;
  session_id?: string | null;
}

export interface PreviewSession {
  session_id: string;
  collection_ref: string;
  classification_enabled: boolean;
  estimated_total: number | null;
  loaded_count: number;
  next_cursor: string | null;
  has_more: boolean;
}

export interface PreviewItem {
  upstream_item_id: string;
  image_uris: string[];
  metadata: Record<string, unknown>;
}

export interface PreviewItemsPage {
  items: PreviewItem[];
  next_cursor: string | null;
  has_more: boolean;
  estimated_total: number | null;
}

export interface SparseSummaryResponse {
  dataset_id: string;
  name: string;
  dataset_type: string;
  storage_mode: string;
  manifest: {
    shard_count: number;
    total_rows: number;
    created_at: string;
    schema_columns: { name: string; type: string }[];
  };
  shards: { shard_index: number; row_count: number; format: string; byte_size: number }[];
  sample_rows: Record<string, unknown>[];
}

export * from "./ui-types";
