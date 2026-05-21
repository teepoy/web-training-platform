export type {
  AgentContext,
  AgentPanelDescriptor,
  Annotation,
  AnnotationVersion,
  ArtifactRef,
  BulkAnnotationItem,
  BulkAnnotationRequest,
  BulkAnnotationResponse,
  BulkCreateSampleItem,
  BulkCreateSampleResponse,
  CreatePredictionCollectionRequest,
  DashboardResponse,
  Dataset,
  DatasetAnnotationStats,
  DatasetType,
  ExportFormat,
  GlobalChatRequest,
  JobQueueStats,
  JobStatus,
  LatestAnnotation,
  LoginResponse,
  Model,
  ModelFramework,
  ModelUploadProfile,
  ModelUploadTemplate,
  OrgMember,
  OrgMembership,
  OrgRole,
  Organization,
  PersonalAccessToken,
  PersonalAccessTokenCreated,
  PredictSingleRequest,
  PredictionCollection,
  PredictionEvent,
  PredictionJob,
  PredictionResult,
  RecentJobSummary,
  ReviewAction,
  RunLog,
  RunPredictionRequest,
  Sample,
  SampleWithLabels,
  SaveReviewAnnotationItem,
  SaveReviewAnnotationsResponse,
  Schedule,
  ScheduleRun,
  ServiceStatus,
  SparseSummaryResponse,
  SurfaceStateDocument,
  SyncPredictionCollectionResponse,
  SyncResult,
  TaskSpec,
  TaskTrackerCheckResult,
  TaskTrackerDeepLinks,
  TaskTrackerDerived,
  TaskTrackerDetail,
  TaskTrackerNode,
  TaskTrackerRawPayload,
  TaskTrackerScorecard,
  TaskTrackerStage,
  TaskTrackerSummary,
  TaskTrackerSummaryMetrics,
  TaskType,
  TrainingJob,
  User,
  UserWithOrgs,
  VersionExportResponse,
  WorkPoolStatus,
} from "./shared/api/types";

export type {
  BrowserItem,
  ChatEntry,
  TrainingEvent,
  WaferPoint,
} from "./shared/types/components";

export type {
  PreviewItem,
  PreviewItemsPage,
  PreviewPersistScope,
  PreviewPersistStatus,
  PreviewSession,
} from "./shared/api/preview";

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

export * from "./ui-types";
