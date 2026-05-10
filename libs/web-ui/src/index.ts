export { default as PluginFlowModal } from "./components/plugin-flow-modal";
export { default as PluginTypeSelector } from "./components/plugin-type-selector";
export type { PluginCard, PluginKind } from "./plugin-flow";

export { default as DatasetPageShell } from "./components/datasets/dataset-page-shell";
export { default as DatasetRowActions } from "./components/datasets/dataset-row-actions";
export { default as DatasetTable } from "./components/datasets/dataset-table";
export { default as DatasetToolbar } from "./components/datasets/dataset-toolbar";
export { default as AgentChatDrawer } from "./components/agent-chat-drawer";
export { default as AnnotationGrid } from "./components/annotation-grid";
export { default as BrowserSidebar } from "./components/browser-sidebar";
export { default as PreviewItemDrawer } from "./components/preview-item-drawer";
export { default as SampleBrowser } from "./components/sample-browser";
export { default as TrainingChart } from "./components/training-chart";
export { default as WidgetErrorBoundary } from "./components/widget-error-boundary";
export { handleBrowserActivation } from "./utils/browser-activation";
export type { ActivationCallbacks, ActivationEvent, ActivationMode } from "./utils/browser-activation";

export type {
  DatasetListItem,
  DatasetListPermissions,
  DatasetListUser,
  DatasetPageShellProps,
  DatasetPlugin,
  DatasetToolbarProps,
  MaybeRef,
  UseDatasetListSurfaceOptions,
  UseDatasetListSurfaceResult,
} from "./datasets/types";

export { buildDatasetColumns, resolveDefaultDatasetTaskType, useDatasetListSurface } from "./datasets/surface";

export { annotationProgressPlugin } from "./plugins/sidebar-annotation-progress";
export { browserSummaryPlugin } from "./plugins/sidebar-browser-summary";
export { dataTablePlugin } from "./plugins/sidebar-data-table";
export { echartsGenericPlugin } from "./plugins/sidebar-echarts-generic";
export { interactiveScatterPlugin } from "./plugins/sidebar-interactive-scatter";
export { labelDistributionPlugin } from "./plugins/sidebar-label-distribution";
export { markdownLogPlugin } from "./plugins/sidebar-markdown-log";
export { metricCardsPlugin } from "./plugins/sidebar-metric-cards";
export { predictionSummaryPlugin } from "./plugins/sidebar-prediction-summary";
export { sampleViewerPlugin } from "./plugins/sidebar-sample-viewer";
export { waferMapPlugin } from "./plugins/sidebar-wafer-map";

export { default as AnnotationProgressWidget } from "./plugins/sidebar-annotation-progress/AnnotationProgressWidget.vue";
export { default as BrowserSummaryWidget } from "./plugins/sidebar-browser-summary/BrowserSummaryWidget.vue";
export { default as DataTableWidget } from "./plugins/sidebar-data-table/DataTableWidget.vue";
export { default as GenericEChartsWidget } from "./plugins/sidebar-echarts-generic/GenericEChartsWidget.vue";
export { default as InteractiveScatterWidget } from "./plugins/sidebar-interactive-scatter/InteractiveScatterWidget.vue";
export { default as LabelDistributionWidget } from "./plugins/sidebar-label-distribution/LabelDistributionWidget.vue";
export { default as MarkdownLogWidget } from "./plugins/sidebar-markdown-log/MarkdownLogWidget.vue";
export { default as MetricCardsWidget } from "./plugins/sidebar-metric-cards/MetricCardsWidget.vue";
export { default as PredictionSummaryWidget } from "./plugins/sidebar-prediction-summary/PredictionSummaryWidget.vue";
export { default as SampleViewerWidget } from "./plugins/sidebar-sample-viewer/SampleViewerWidget.vue";
export { default as WaferMapWidget } from "./plugins/sidebar-wafer-map/WaferMapWidget.vue";

export type {
  AnnotationGridItem,
  AgentChatStatus,
  BrowserItem,
  ChatEntry,
  PreviewItem,
  RunLog,
  SidebarPanelDescriptor,
  TrainingEvent,
} from "./types/components";

export type {
  AnnotationGridItem as SidebarAnnotationGridItem,
  ClassifyDashboardContext,
  ClassifyDashboardStats,
  MarkdownLogEntry,
  MetricCardItem,
} from "./types/sidebar-widgets";
