import { defineAsyncComponent, type Component } from "vue";

export const widgetComponentMap: Record<string, Component> = {
  "annotation-progress": defineAsyncComponent(
    () => import("@/shared/components/annotation-progress/AnnotationProgressWidget.vue"),
  ),
  "browser-summary": defineAsyncComponent(
    () => import("@/shared/components/browser-summary/BrowserSummaryWidget.vue"),
  ),
  "data-table": defineAsyncComponent(
    () => import("@/shared/components/data-table/DataTableWidget.vue"),
  ),
  "echarts-generic": defineAsyncComponent(
    () => import("@/shared/components/echarts-generic/GenericEChartsWidget.vue"),
  ),
  "interactive-scatter": defineAsyncComponent(
    () => import("@/shared/components/interactive-scatter/InteractiveScatterWidget.vue"),
  ),
  "label-distribution": defineAsyncComponent(
    () => import("@/shared/components/label-distribution/LabelDistributionWidget.vue"),
  ),
  "markdown-log": defineAsyncComponent(
    () => import("@/shared/components/markdown-log/MarkdownLogWidget.vue"),
  ),
  "metric-cards": defineAsyncComponent(
    () => import("@/shared/components/metric-cards/MetricCardsWidget.vue"),
  ),
  "prediction-summary": defineAsyncComponent(
    () => import("@/shared/components/prediction-summary/PredictionSummaryWidget.vue"),
  ),
  "sample-viewer": defineAsyncComponent(
    () => import("@/shared/components/sample-viewer/SampleViewerWidget.vue"),
  ),
  "wafer-map": defineAsyncComponent(
    () => import("@/shared/components/wafer-map/WaferMapWidget.vue"),
  ),
};
