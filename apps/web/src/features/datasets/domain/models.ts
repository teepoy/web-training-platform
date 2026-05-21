export type TaskType = "classification" | "vqa" | "detection";
export type DatasetType = "image_classification" | "image_vqa" | "image_detection";
export type DatasetStorageMode = "db_full" | "file_shard_sparse";

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
  storage_mode?: DatasetStorageMode;
  capabilities?: Record<string, boolean>;
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

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
}

export interface DatasetAnnotationStats {
  total_samples: number;
  annotated_samples: number;
  unlabeled_samples: number;
  label_counts: Record<string, number>;
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

export interface CreateDatasetBody {
  name: string;
  dataset_type: DatasetType;
  task_spec?: TaskSpec;
  storage_mode?: DatasetStorageMode;
}

export interface CreateSampleBody {
  image_uris: string[];
  metadata?: Record<string, unknown>;
}

export interface UploadResponse {
  uri: string;
  sample_id: string;
  index: number;
}

export interface DatasetExport {
  dataset: Dataset;
  samples: Sample[];
  annotations: Annotation[];
}

export interface PersistExportResponse {
  uri: string;
}

export interface ExportFormatItem {
  format_id: string;
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

export interface DashboardResponse {
  work_pool: import("@/types").WorkPoolStatus | null;
  job_queue: import("@/types").JobQueueStats;
  recent_jobs: import("@/types").RecentJobSummary[];
  services: import("@/types").ServiceStatus[];
  prefect_connected: boolean;
}
