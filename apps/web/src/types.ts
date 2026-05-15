import type { AgentPanelDescriptor } from "@platform/web-ui";

// ---------------------------------------------------------------------------
// Type aliases
// ---------------------------------------------------------------------------
export type {
  TaskType, DatasetType, DatasetStorageMode, ModelFramework, JobStatus,
  ScheduleStatus, ModelFormat,
} from "@platform/web-ui";

// ---------------------------------------------------------------------------
// Core domain
// ---------------------------------------------------------------------------
export type {
  Dataset, Sample, SampleWithLabels, LatestAnnotation, TaskSpec,
  PaginatedResponse, ApiError, HealthStatus, UploadResponse, UpdateAnnotationPayload,
} from "@platform/web-ui";

// ---------------------------------------------------------------------------
// Annotation (kept local — @platform/web-ui has two `Annotation` types:
// the domain annotation and useDataPipeline.Annotation<TId>)
// ---------------------------------------------------------------------------
export interface Annotation {
  id: string;
  sample_id: string;
  label: string;
  created_by: string;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Sparse dataset
// ---------------------------------------------------------------------------
export type {
  SparseShardSummary, SparseManifestSummary, SparseSummaryResponse,
  SparsePredictionResult, SparsePredictionShard, SparsePredictionJobResult,
} from "@platform/web-ui";

// ---------------------------------------------------------------------------
// Bulk ops & annotations
// ---------------------------------------------------------------------------
export type {
  BulkCreateSampleItem, BulkCreateSampleResponse,
  BulkAnnotationItem, BulkAnnotationRequest, BulkAnnotationResponse,
  SyncResult, DatasetAnnotationStats,
} from "@platform/web-ui";

// ---------------------------------------------------------------------------
// Training & presets
// ---------------------------------------------------------------------------
export type {
  TrainingPreset, TrainingJob, ModelSpec, ArtifactRef, SampleFeature,
  PresetModelSource, PresetTrainConfig, PresetPredictConfig,
  PresetPredictTarget, PresetRuntimeConfig, PresetCompatibility,
} from "@platform/web-ui";

// ---------------------------------------------------------------------------
// Models
// ---------------------------------------------------------------------------
export type {
  Model, ModelUploadTemplate, ModelUploadProfile,
  UploadModelMetadata, UploadedModelSpec, ModelCompatibility,
} from "@platform/web-ui";

// ---------------------------------------------------------------------------
// Dashboard & schedules
// ---------------------------------------------------------------------------
export type {
  DashboardResponse, WorkPoolStatus, JobQueueStats, RecentJobSummary, ServiceStatus,
  Schedule, ScheduleRun,
} from "@platform/web-ui";

// ---------------------------------------------------------------------------
// Task tracker
// ---------------------------------------------------------------------------
export type {
  TaskTrackerSummary, TaskTrackerDetail, TaskTrackerNode, TaskTrackerStage,
} from "@platform/web-ui";

// ---------------------------------------------------------------------------
// Display / UI components
// ---------------------------------------------------------------------------
export type {
  AnnotationGridItem, BrowserItem, ChatEntry, RunLog,
  SidebarPanelDescriptor, TrainingEvent, MarkdownLogEntry, MetricCardItem,
} from "@platform/web-ui";

// ---------------------------------------------------------------------------
// Agent & wafer
// ---------------------------------------------------------------------------
export type {
  SurfaceStateDocument, AgentContext, GlobalChatRequest,
  WaferPoint, WaferPointsQueryResponse,
} from "@platform/web-ui";

export type { AgentPanelDescriptor } from "@platform/web-ui";

// ---------------------------------------------------------------------------
// Predictions (from @platform/web-data)
// ---------------------------------------------------------------------------
export {
  type PredictionResult, type PredictionJob, type PredictionEvent,
  type RunPredictionRequest, type PredictSingleRequest,
  type ReviewAction, type AnnotationVersion,
  type SaveReviewAnnotationItem, type SaveReviewAnnotationsResponse,
  type PredictionCollection, type CreatePredictionCollectionRequest,
  type SyncPredictionCollectionResponse,
  type ExportFormat, type VersionExportResponse,
} from "@platform/web-ui/api/predictions";

// ---------------------------------------------------------------------------
// Auth (from @platform/web-data)
// ---------------------------------------------------------------------------
export {
  type OrgRole, type User, type Organization,
  type OrgMembership, type UserWithOrgs, type LoginResponse,
  type PersonalAccessToken, type PersonalAccessTokenCreated, type OrgMember,
} from "@platform/web-ui/api/auth";

// ---------------------------------------------------------------------------
// Preview (from @platform/web-data)
// ---------------------------------------------------------------------------
export {
  type PreviewSession, type PreviewItemsPage,
  type PreviewPersistScope, type PreviewPersistStatus,
} from "@platform/web-ui/api/preview";

// ---------------------------------------------------------------------------
// App-local UI contracts
// ---------------------------------------------------------------------------

/** SSE event protocol for agent chat streaming. */
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
  panels: AgentPanelDescriptor[];
}

export interface AgentDoneEvent extends AgentChatEvent {
  type: "done";
}

/** Table widget interaction protocol. */
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
