/**
 * Widget Component Map
 *
 * Maps widget component keys (strings used in SidebarPanelDescriptor.component)
 * to their lazily-loaded Vue components.
 *
 * This replaces the global widgetRegistry.getWidgetComponent(key) lookup
 * with a simple static record, enabling Stage 3 to remove the registration
 * and registry system entirely.
 *
 * Usage:
 *   import { widgetComponentMap } from "./widgetMap";
 *   const comp = widgetComponentMap[key] ?? null;
 *
 * All 12 widgets registered in @platform/web-ui are included:
 *   - Sidebar panel presets (annotation-progress, label-distribution, wafer-map,
 *     sample-viewer, blink-table, browser-summary)
 *   - Agent-injectable panels (echarts-generic, markdown-log, data-table,
 *     metric-cards, interactive-scatter, prediction-summary)
 */

import { defineAsyncComponent, type Component } from "vue";

export const widgetComponentMap: Record<string, Component> = {
  "annotation-progress": defineAsyncComponent(
    () => import("@platform/web-ui/components/annotation-progress/AnnotationProgressWidget.vue"),
  ),
  "browser-summary": defineAsyncComponent(
    () => import("@platform/web-ui/components/browser-summary/BrowserSummaryWidget.vue"),
  ),
  "data-table": defineAsyncComponent(
    () => import("@platform/web-ui/components/data-table/DataTableWidget.vue"),
  ),
  "echarts-generic": defineAsyncComponent(
    () => import("@platform/web-ui/components/echarts-generic/GenericEChartsWidget.vue"),
  ),
  "interactive-scatter": defineAsyncComponent(
    () => import("@platform/web-ui/components/interactive-scatter/InteractiveScatterWidget.vue"),
  ),
  "label-distribution": defineAsyncComponent(
    () => import("@platform/web-ui/components/label-distribution/LabelDistributionWidget.vue"),
  ),
  "markdown-log": defineAsyncComponent(
    () => import("@platform/web-ui/components/markdown-log/MarkdownLogWidget.vue"),
  ),
  "metric-cards": defineAsyncComponent(
    () => import("@platform/web-ui/components/metric-cards/MetricCardsWidget.vue"),
  ),
  "prediction-summary": defineAsyncComponent(
    () => import("@platform/web-ui/components/prediction-summary/PredictionSummaryWidget.vue"),
  ),
  "sample-viewer": defineAsyncComponent(
    () => import("@platform/web-ui/components/sample-viewer/SampleViewerWidget.vue"),
  ),
  "wafer-map": defineAsyncComponent(
    () => import("@platform/web-ui/components/wafer-map/WaferMapWidget.vue"),
  ),
  "blink-table": defineAsyncComponent(
    () => import("@platform/web-ui/components/blink-table/BlinkTableWidget.vue"),
  ),
};
