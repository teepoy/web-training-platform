/**
 * Frontend type definitions.
 * UI helper types have moved to `./ui-helpers`.
 */
import type {
  TaskTrackerRawPayload,
  TaskTrackerDerived,
  UserResponse as User,
} from "@/generated/orval/models";

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
}

export interface SyncResult {
  synced_count: number;
  skipped_count?: number;
  errors: string[];
}

export interface Trainer {
  id: string;
  name: string;
  view_type: string;
  trainable: boolean;
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

export interface VersionExportResponse {
  uri: string;
  format_id: string;
}

export type TaskType = "classification" | "vqa" | "detection" | "patch";
export type DatasetType = "image_classification" | "image_vqa" | "image_detection" | "image_sc";
export type ModelFramework = "pytorch" | "dspy";
export type ModelFormat = "pytorch" | "onnx" | "safetensors" | "keras";

export interface HealthStatus {
  status: string;
}

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

export interface SampleFeature {
  sample_id: string;
  embedding: number[];
}

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

export interface CreateSubscriptionBody {
  workflow_type: string;
  filter_config?: Record<string, unknown>;
  enabled?: boolean;
}

export interface UpdateSubscriptionBody {
  filter_config?: Record<string, unknown>;
  enabled?: boolean;
}

export interface LabeledImageV1Row {
  sample_id: string;
  image_uris: string[];
  label: string;
}

export interface QAInputV1Row {
  sample_id: string;
  image_uris: string[];
  question: string;
}

export interface BoxV1Row {
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface BoxDetectionV1Row {
  sample_id: string;
  image_uris: string[];
  boxes: BoxV1Row[];
  width?: number | null;
  height?: number | null;
}

export interface ImageInputV1Row {
  sample_id: string;
  image_uris: string[];
}

export interface WaferPointsQueryResponse {
  points: import("../types/components").WaferPoint[];
  total: number;
}

// eslint-disable-next-line @typescript-eslint/no-empty-object-type
export type ViewRowV1 = LabeledImageV1Row | QAInputV1Row | BoxDetectionV1Row | ImageInputV1Row;

export interface ViewPaginatedResponse<T extends ViewRowV1 = ViewRowV1> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  view_type: string;
  dataset_id: string;
}
