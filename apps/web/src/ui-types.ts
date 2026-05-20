import type { components } from "./generated/openapi-types";

export type ModelFramework = "pytorch" | "dspy";

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
  model_spec?: ModelSpec | { framework: string; base_model: string };
  omegaconf_yaml?: string;
  dataloader_ref?: string;
  org_id?: string | null;
}

export interface SampleFeature {
  sample_id: string;
  embedding: number[];
}

export interface ApiError {
  detail: string;
  status: number;
}

export interface HealthStatus {
  status: string;
  auth_enabled: boolean;
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

export interface SyncResult {
  synced_count: number;
  skipped_count?: number;
  errors: string[];
}

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

export interface UploadModelMetadata {
  name: string;
  format: ModelFormat;
  job_id: string;
  template_id: string;
  profile_id: string;
  model_spec: UploadedModelSpec;
  compatibility: ModelCompatibility;
}

export interface BatchPredictionResult {
  model_id: string;
  dataset_id: string;
  total_samples: number;
  successful: number;
  failed: number;
  predictions: components["schemas"]["PredictionResultResponse"][];
  started_at: string;
  completed_at: string;
  model_version: string | null;
}

export interface VersionExportResponse {
  uri: string;
  format_id: string;
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

export type PreviewPersistScope = "entire_collection" | "loaded_items_only";

type PersistStatusSchema = components["schemas"]["PersistStatusResponse"];

export type PreviewPersistStatus = Omit<PersistStatusSchema, "status"> & {
  status: "pending" | "running" | "completed" | "failed";
};

export interface AgentChatEvent {
  type: "agent-message" | "agent-action" | "sidebar-update" | "done";
}

export interface AgentMessageEvent extends AgentChatEvent {
  type: "agent-message";
  content: string;
}

export interface AgentActionEvent extends AgentChatEvent {
  type: "agent-action";
  tool: string;
  summary: string;
}

export interface AgentSidebarUpdateEvent extends AgentChatEvent {
  type: "sidebar-update";
  surface_id: string;
  panels: components["schemas"]["AgentPanelDescriptor"][];
}

export interface AgentDoneEvent extends AgentChatEvent {
  type: "done";
}

export interface ChatEntry {
  id: string;
  role: "user" | "assistant" | "action";
  content: string;
  tool?: string;
  timestamp: number;
}

export interface MarkdownLogEntry {
  ts: string;
  level: string;
  message: string;
}

export interface MetricCardItem {
  label: string;
  value: string;
  color?: string;
}

export type TableWidgetEntity = "sample" | "prediction" | "row";

export type TableWidgetFilterMode = "all" | "selected-only";

export interface TableWidgetInteractionConfig {
  collection: string;
  entity: TableWidgetEntity;
  emitSelection?: boolean;
  followSelection?: boolean;
  filterFromSelection?: boolean;
  clearFilterOnEmptySelection?: boolean;
}

export interface TableWidgetColumn {
  key: string;
  label: string;
}

export interface TableWidgetRow {
  id: string;
  cells: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

export interface InteractiveTableWidgetData {
  columns: TableWidgetColumn[];
  rows: TableWidgetRow[];
}

export interface AnnotationGridItem {
  id: string;
  imageSrcs: string[];
  currentLabel: string | null;
  draftLabel: string | null;
  predictionLabel: string | null;
  predictionConfidence: number | null;
  predictionId: string | null;
  metadata: Record<string, unknown>;
}

export interface BrowserItem {
  id: string;
  imageSrcs: string[];
  metadata: Record<string, unknown>;
  sourceKind?: "dataset" | "preview" | "classify-review";
  currentLabel: string | null;
  draftLabel: string | null;
  predictionLabel: string | null;
  predictionConfidence: number | null;
  predictionId: string | null;
  activationLabel: string | null;
}
