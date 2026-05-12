export { default as PanelHost } from "./components/panel-host";
export { default as FlowModal } from "./components/flow-modal";
export { default as FlowTypeSelector } from "./components/flow-type-selector";
export type { FlowCard, FlowKind } from "./flow";

export { default as DatasetPageShell } from "./components/datasets/dataset-page-shell";
export { default as DatasetRowActions } from "./components/datasets/dataset-row-actions";
export { default as DatasetTable } from "./components/datasets/dataset-table";
export { default as DatasetToolbar } from "./components/datasets/dataset-toolbar";
export { default as AgentChatDrawer } from "./components/agent-chat-drawer";
export { default as AnnotationGrid } from "./components/annotation-grid";
export { default as BrowserSidebar } from "./components/browser-sidebar";
export { BlinkImageCell, BlinkTable } from "./components/blink-table";
export { default as PreviewItemDrawer } from "./components/preview-item-drawer";
export { default as SampleBrowser } from "./components/sample-browser";
export { default as TrainingChart } from "./components/training-chart";
export { default as WidgetErrorBoundary } from "./components/widget-error-boundary";
export { handleBrowserActivation } from "./utils/browser-activation";
export {
  COLLAPSED_SIDEBAR_WIDTH,
  DEFAULT_SIDEBAR_WIDTH,
  MAX_SIDEBAR_WIDTH,
  MIN_SIDEBAR_WIDTH,
  useSampleBrowserPrefs,
} from "./stores/sampleBrowser";
export {
  FALLBACK_PLACEHOLDER,
  listImageAdapters,
  registerImageAdapter,
  resolveImageUri,
  resolveImageUris,
  unregisterImageAdapter,
} from "./utils/image-adapters";
export type { ImageAdapter } from "./utils/image-adapters";
export { filterBrowserItems } from "./utils/browser-filter";
export type { BrowserFilterParams } from "./utils/browser-filter";
export { buildBlinkTableData } from "./utils/blink-table-data";
export type {
  BlinkSampleInput,
  BlinkTableDataResult,
  BuildBlinkTableDataOptions,
} from "./utils/blink-table-data";
export { useBlinkController } from "./composables/useBlinkController";
export type {
  UseBlinkControllerOptions,
  UseBlinkControllerReturn,
} from "./composables/useBlinkController";

export { usePagePanels } from "./composables/usePagePanels";
export type {
  UsePagePanelsOptions,
  UsePagePanelsReturn,
} from "./composables/usePagePanels";
export {
  injectWaferPanelData,
  metadataNumber,
  metadataString,
  normalizeWaferPoint,
} from "./composables/useWaferHelpers";
export { default as PageProvider } from "./components/page-provider/PageProvider.vue";
export type {
  ActivationCallbacks,
  ActivationEvent,
  ActivationMode,
} from "./utils/browser-activation";

export type {
  DatasetListItem,
  DatasetListPermissions,
  DatasetListUser,
  DatasetPageShellProps,
  DatasetFlow,
  DatasetToolbarProps,
  MaybeRef,
  UseDatasetListSurfaceOptions,
  UseDatasetListSurfaceResult,
} from "./datasets/types";

export {
  buildDatasetColumns,
  resolveDefaultDatasetTaskType,
  useDatasetListSurface,
} from "./datasets/surface";

export { annotationProgressPlugin } from "./components/annotation-progress";
export { browserSummaryPlugin } from "./components/browser-summary";
export { dataTablePlugin } from "./components/data-table";
export { echartsGenericPlugin } from "./components/echarts-generic";
export { interactiveScatterPlugin } from "./components/interactive-scatter";
export { labelDistributionPlugin } from "./components/label-distribution";
export { markdownLogPlugin } from "./components/markdown-log";
export { metricCardsPlugin } from "./components/metric-cards";
export { predictionSummaryPlugin } from "./components/prediction-summary";
export { sampleViewerPlugin } from "./components/sample-viewer";
export { waferMapPlugin } from "./components/wafer-map";
export { blinkTablePlugin } from "./components/blink-table";

export { default as AnnotationProgressWidget } from "./components/annotation-progress/AnnotationProgressWidget.vue";
export { default as BrowserSummaryWidget } from "./components/browser-summary/BrowserSummaryWidget.vue";
export { default as DataTableWidget } from "./components/data-table/DataTableWidget.vue";
export { default as GenericEChartsWidget } from "./components/echarts-generic/GenericEChartsWidget.vue";
export { default as InteractiveScatterWidget } from "./components/interactive-scatter/InteractiveScatterWidget.vue";
export { default as LabelDistributionWidget } from "./components/label-distribution/LabelDistributionWidget.vue";
export { default as MarkdownLogWidget } from "./components/markdown-log/MarkdownLogWidget.vue";
export { default as MetricCardsWidget } from "./components/metric-cards/MetricCardsWidget.vue";
export { default as PredictionSummaryWidget } from "./components/prediction-summary/PredictionSummaryWidget.vue";
export { default as SampleViewerWidget } from "./components/sample-viewer/SampleViewerWidget.vue";
export { default as WaferMapWidget } from "./components/wafer-map/WaferMapWidget.vue";
export { default as BlinkTableWidget } from "./components/blink-table/BlinkTableWidget.vue";

export type {
  AnnotationGridItem,
  AgentChatStatus,
  BrowserItem,
  ChatEntry,
  RunLog,
  SidebarPanelDescriptor,
  TrainingEvent,
  WaferPoint,
} from "./types/components";

export type {
  ClassifyDashboardContext,
  ClassifyDashboardStats,
  MarkdownLogEntry,
  MetricCardItem,
  SidebarAnnotationGridItem,
} from "./types/sidebar-widgets";

export type {
  BlinkColumnDef,
  BlinkPhase,
  BlinkRow,
  BlinkTableProps,
} from "./types/blink-table";
