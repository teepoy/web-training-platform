export { default as AgentChatDrawer } from "./components/agent-chat-drawer";
export { annotationProgressPlugin as AnnotationProgressWidget } from "./components/annotation-progress";
export { default as BrowserSidebar } from "./components/browser-sidebar";
export { browserSummaryPlugin as BrowserSummaryWidget } from "./components/browser-summary";
export { dataTablePlugin as DataTableWidget } from "./components/data-table";
export { default as DatasetPageShell } from "./components/datasets/dataset-page-shell";
export { default as DatasetRowActions } from "./components/datasets/dataset-row-actions";
export { default as DatasetTable } from "./components/datasets/dataset-table";
export { default as DatasetToolbar } from "./components/datasets/dataset-toolbar";
export { default as FlowModal } from "./components/flow-modal";
export { default as FlowTypeSelector } from "./components/flow-type-selector";
export { labelDistributionPlugin as LabelDistributionWidget } from "./components/label-distribution";
export { markdownLogPlugin as MarkdownLogWidget } from "./components/markdown-log";
export { metricCardsPlugin as MetricCardsWidget } from "./components/metric-cards";
export { default as PanelHost } from "./components/panel-host";
export { predictionSummaryPlugin as PredictionSummaryWidget } from "./components/prediction-summary";
export { default as PreviewItemDrawer } from "./components/preview-item-drawer";
export { default as RunLogViewer } from "./components/run-log-viewer";
export { default as SampleBrowser } from "./components/sample-browser";
export { default as SampleDetailDrawer } from "./components/sample-detail-drawer";
export { sampleViewerPlugin as SampleViewerWidget } from "./components/sample-viewer";
export {
  default as TaskInsightModal,
  TASK_INSIGHT_ORG_ID_KEY,
  TASK_INSIGHT_STREAM_KEY,
} from "./components/task-insight-modal";
export { default as TrainingChart } from "./components/training-chart";

export {
  DATA_PIPELINE_KEY,
  createDataPipeline,
  createDataPipeline as useDataPipeline,
} from "./composables/useDataPipeline";
export type { DataPipeline } from "./composables/useDataPipeline";
export {
  injectWaferPanelData,
  metadataNumber,
  metadataString,
  normalizeWaferPoint,
} from "./composables/useWaferHelpers";
export {
  useAgentCore,
  type UseAgentCoreOptions,
  type UseAgentCoreReturn,
} from "./composables/useAgentCore";
export { useClassifyDashboard } from "./composables/useClassifyDashboard";
export { usePreviewLoader } from "./composables/usePreviewLoader";
export { useSampleLoader } from "./composables/useSampleLoader";

export { handleBrowserActivation } from "./components/sample-browser/browser-activation";
export {
  resolveImageUri,
  resolveImageUris,
  registerImageAdapter,
  unregisterImageAdapter,
  listImageAdapters,
  FALLBACK_PLACEHOLDER,
} from "./utils/image-adapters";
export { listDatasets } from "./api/datasets";
export {
  buildDatasetColumns,
  useDatasetListSurface,
  resolveDefaultDatasetTaskType,
} from "./datasets/surface";
export type {
  DatasetListItem,
  DatasetListUser,
  DatasetFlow,
  UseDatasetListSurfaceOptions,
  UseDatasetListSurfaceResult,
  BuildDatasetColumnsOptions,
} from "./datasets/types";
export type { SyncResult, PaginatedResponse } from "./api/types";
export type { DatasetExport, ExportFormatItem } from "./api/ui-helpers";
export {
  listPreviewItems,
  type PreviewItem,
  type PreviewItemsPage,
  type PreviewPersistScope,
  type PreviewPersistStatus,
  type PreviewSession,
  createPreviewSession,
  getPreviewPersistStatus,
  getPreviewSession,
  startPreviewPersist,
} from "./api/preview";
export { GLOBAL_AGENT_PANELS_KEY } from "./keys";

export {
  DEFAULT_SIDEBAR_WIDTH,
  MIN_SIDEBAR_WIDTH,
  MAX_SIDEBAR_WIDTH,
  COLLAPSED_SIDEBAR_WIDTH,
  useSampleBrowserPrefs,
} from "./stores/sampleBrowser";
export {
  BROWSER_DASHBOARD_KEY,
  defineDashboardWidget,
  type DashboardWidgetDescriptor,
  type DashboardWidgetProps,
  type WidgetContract,
  type SidebarWidgetCapability,
  type SidebarWidgetSelfTestScenario,
} from "./widgets/sdk";
export {
  defineImporter,
  type ImporterDescriptor,
  type ImporterSurface,
  type ImporterProps,
  type ImporterResult,
} from "./widgets/sdk";
export {
  defineExporter,
  type ExporterDescriptor,
  type ExporterSurface,
  type ExporterProps,
  type ExporterResult,
} from "./widgets/sdk";
export {
  defineAgentSkill,
  type AgentSkillDescriptor,
  type AgentSkillSurface,
  type AgentSkillResultProps,
} from "./widgets/sdk";
export {
  definePreviewLauncher,
  type PreviewLauncherDescriptor,
  type PreviewLauncherSurface,
  type PreviewLauncherRequiredProps,
  type PreviewLauncherResult,
} from "./widgets/sdk";
export { createDescriptorRegistry, type DescriptorRegistry } from "./widgets/sdk";
export type { FlowCard } from "./flow";
export type {
  AgentChatStatus,
  ChatEntry,
  BrowserItem,
  WaferPoint,
  SidebarPanelDescriptor,
  TrainingEvent,
  RunLog,
  AnnotationGridItem,
} from "./types/components";
