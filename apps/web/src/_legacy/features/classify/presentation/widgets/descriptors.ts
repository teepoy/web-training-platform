import { defineAsyncComponent } from "vue";
import { defineDashboardWidget } from "@/shared/widgets/sdk";

export const annotationProgressPlugin = defineDashboardWidget({
  key: "annotation-progress",
  component: defineAsyncComponent(
    () => import("@/shared/components/annotation-progress/AnnotationProgressWidget.vue"),
  ),
  contract: {
    displayName: "Annotation Progress",
    description: "Shows annotation totals, drafts, selected counts, and label breakdowns.",
    acceptsProps: [
      "chartType",
      "showCounts",
      "showPercent",
      "includeDrafts",
      "showLabelBreakdown",
    ],
    capabilities: { reads: ["classify-dashboard"], emits: [] },
    selfTests: [
      {
        name: "renders dashboard metrics",
        objective: "Verify the widget renders shared dashboard stats and selection counts.",
        steps: [
          "Provide annotation stats with non-zero totals and selectedCount in the shared context.",
          "Render the widget with showCounts enabled.",
        ],
        expected: [
          "Metric values are visible for annotated, remaining, total, and selected counts when present.",
          "The widget renders without requiring agent-only data.",
        ],
      },
    ],
  },
});

export const browserSummaryPlugin = defineDashboardWidget({
  key: "browser-summary",
  component: defineAsyncComponent(
    () => import("@/shared/components/browser-summary/BrowserSummaryWidget.vue"),
  ),
  contract: {
    displayName: "Browser Summary",
    description: "Compact read-only widget showing loaded item count, visible count, and active filter label.",
    acceptsProps: ["totalLoaded", "filteredCount"],
    capabilities: { reads: ["browser-dashboard"], emits: [] },
    selfTests: [
      {
        name: "renders item counts",
        objective: "Verify the widget shows loaded and filtered counts from injected browser dashboard context.",
        steps: ["Provide browser-dashboard context with totalLoaded and filteredCount values.", "Render the widget without additional props."],
        expected: ["The widget displays 'Showing X of Y items' without errors.", "When context is absent the widget degrades gracefully showing '—'."],
      },
    ],
  },
});

export const dataTablePlugin = defineDashboardWidget({
  key: "data-table",
  component: defineAsyncComponent(
    () => import("@/shared/components/data-table/DataTableWidget.vue"),
  ),
  contract: {
    displayName: "Data Table",
    description: "Renders columns and rows from static or agent-supplied data, including linked interactive table mode.",
    acceptsProps: ["data", "config", "size"],
    capabilities: {
      reads: ["interaction-state"],
      emits: ["select-samples", "select-predictions", "apply-filter", "clear-selection"],
    },
    selfTests: [
      {
        name: "renders a table row",
        objective: "Verify the widget handles a minimal columns-and-rows payload.",
        steps: ["Render the widget with one column and one row."],
        expected: ["The first row is visible and the widget does not crash on a small dataset."],
      },
      {
        name: "interactive row selection",
        objective: "Verify row click can emit linked intents and follow shared collection selection state.",
        steps: ["Render the widget with object columns, row ids, and config.interaction.collection.", "Click a row and inspect emitted intent metadata."],
        expected: ["The widget emits select-* intents with metadata.collection.", "Rows in shared selection state are highlighted when followSelection is enabled."],
      },
    ],
  },
});

export const echartsGenericPlugin = defineDashboardWidget({
  key: "echarts-generic",
  component: defineAsyncComponent(
    () => import("@/shared/components/echarts-generic/GenericEChartsWidget.vue"),
  ),
  contract: {
    displayName: "Generic ECharts",
    description: "Renders generic ECharts option payloads for static or agent-driven panels.",
    acceptsProps: ["data", "config", "size"],
    capabilities: { reads: [], emits: [] },
    selfTests: [
      {
        name: "renders minimal chart payload",
        objective: "Verify the widget accepts a minimal chart option payload.",
        steps: ["Render the widget with a minimal ECharts option object in panel data."],
        expected: ["The widget renders a chart container without contract validation failures."],
      },
    ],
  },
});

export const interactiveScatterPlugin = defineDashboardWidget({
  key: "interactive-scatter",
  component: defineAsyncComponent(
    () => import("@/shared/components/interactive-scatter/InteractiveScatterWidget.vue"),
  ),
  contract: {
    displayName: "Interactive Scatter",
    description: "Renders metadata-driven scatter points and emits linked sample selection/filter intents.",
    acceptsProps: ["data", "config", "size"],
    capabilities: { reads: ["interaction-state"], emits: ["select-samples", "apply-filter", "clear-selection"] },
    selfTests: [
      {
        name: "point click updates linked sample selection",
        objective: "Verify clicking a plotted point emits sample-selection intents for the shared collection.",
        steps: ["Render the widget with inline points and config.interaction.collection set.", "Click one scatter point."],
        expected: ["The widget emits select-samples for the clicked point.", "When filterFromSelection is enabled, the linked sample-viewer can reduce to the selected sample ids."],
      },
    ],
  },
});

export const labelDistributionPlugin = defineDashboardWidget({
  key: "label-distribution",
  component: defineAsyncComponent(
    () => import("@/shared/components/label-distribution/LabelDistributionWidget.vue"),
  ),
  contract: {
    displayName: "Label Distribution",
    description: "Displays label counts and supports click-to-filter for the classify surface.",
    acceptsProps: ["orientation", "showValues", "maxBars"],
    capabilities: { reads: ["classify-dashboard", "interaction-state"], emits: ["select-labels", "clear-selection"] },
    selfTests: [
      {
        name: "renders sorted labels",
        objective: "Verify label counts render and overflow labels can be grouped.",
        steps: ["Provide more labels than maxBars in the shared dashboard stats.", "Render the widget in horizontal orientation."],
        expected: ["The widget renders without errors.", "The chart can group remaining labels into an Other bucket."],
      },
      {
        name: "click to filter",
        objective: "Verify a chart click can update the shared label filter state.",
        steps: ["Provide a shared interaction-state with no activeLabelFilter.", "Click a concrete label bar in the chart."],
        expected: ["The widget emits a select-labels intent through the shared interaction context.", "The active label is visually emphasized once the interaction state updates."],
      },
    ],
  },
});

export const markdownLogPlugin = defineDashboardWidget({
  key: "markdown-log",
  component: defineAsyncComponent(
    () => import("@/shared/components/markdown-log/MarkdownLogWidget.vue"),
  ),
  contract: {
    displayName: "Markdown Log",
    description: "Displays log entries or markdown updates in a scrollable widget.",
    acceptsProps: ["data", "config", "size"],
    capabilities: { reads: [], emits: [] },
    selfTests: [
      {
        name: "renders markdown rows",
        objective: "Verify one or more markdown entries can be shown without layout errors.",
        steps: ["Render the widget with a small list of timestamped log entries."],
        expected: ["The widget renders log content without requiring extra shared context."],
      },
    ],
  },
});

export const metricCardsPlugin = defineDashboardWidget({
  key: "metric-cards",
  component: defineAsyncComponent(
    () => import("@/shared/components/metric-cards/MetricCardsWidget.vue"),
  ),
  contract: {
    displayName: "Metric Cards",
    description: "Displays a compact grid of key metric values.",
    acceptsProps: ["data", "config", "size"],
    capabilities: { reads: [], emits: [] },
    selfTests: [
      {
        name: "renders metric cards",
        objective: "Verify metric labels and values appear for a minimal card set.",
        steps: ["Render the widget with at least one metric card payload."],
        expected: ["Metric labels and values are visible without requiring additional context."],
      },
    ],
  },
});

export const predictionSummaryPlugin = defineDashboardWidget({
  key: "prediction-summary",
  component: defineAsyncComponent(
    () => import("@/shared/components/prediction-summary/PredictionSummaryWidget.vue"),
  ),
  contract: {
    displayName: "Prediction Summary",
    description: "Summarizes totals, edited rows, accepted rows, and confidence in prediction review.",
    acceptsProps: [],
    capabilities: { reads: ["prediction-grid-items"], emits: [] },
    selfTests: [
      {
        name: "renders review totals",
        objective: "Verify accepted and edited counts reflect injected review grid items.",
        steps: ["Provide prediction-grid-items containing accepted and edited items.", "Render the widget without additional props."],
        expected: ["Total, Accepted, and Edited values are computed from injected grid items."],
      },
    ],
  },
});

export const sampleViewerPlugin = defineDashboardWidget({
  key: "sample-viewer",
  component: defineAsyncComponent(
    () => import("@/shared/components/sample-viewer/SampleViewerWidget.vue"),
  ),
  contract: {
    displayName: "Sample Viewer",
    description: "Shows sample thumbnails or item previews inside the sidebar.",
    acceptsProps: ["data", "config", "size"],
    capabilities: { reads: ["classify-dashboard"], emits: [] },
    selfTests: [
      {
        name: "renders a sample preview",
        objective: "Verify at least one sample can be shown from panel data.",
        steps: ["Render the widget with one valid sample payload."],
        expected: ["A preview element is visible and the widget renders without extra agent wiring."],
      },
    ],
  },
});



export const classifyWidgetDescriptors = [
  annotationProgressPlugin,
  browserSummaryPlugin,
  dataTablePlugin,
  echartsGenericPlugin,
  interactiveScatterPlugin,
  labelDistributionPlugin,
  markdownLogPlugin,
  metricCardsPlugin,
  predictionSummaryPlugin,
  sampleViewerPlugin,
] as const;
