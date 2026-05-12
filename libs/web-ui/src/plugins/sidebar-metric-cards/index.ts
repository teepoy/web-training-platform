import { defineAsyncComponent } from "vue";
import { defineSidebarPlugin } from "@platform/plugin-sdk";

export const metricCardsPlugin = defineSidebarPlugin({
  key: "metric-cards",
  component: defineAsyncComponent(
    () => import("../../components/metric-cards/MetricCardsWidget.vue"),
  ),
  contract: {
    displayName: "Metric Cards",
    description: "Displays a compact grid of key metric values.",
    acceptsProps: ["data", "config", "size"],
    capabilities: {
      reads: [],
      emits: [],
    },
    selfTests: [
      {
        name: "renders metric cards",
        objective:
          "Verify metric labels and values appear for a minimal card set.",
        steps: ["Render the widget with at least one metric card payload."],
        expected: [
          "Metric labels and values are visible without requiring additional context.",
        ],
      },
    ],
  },
});
