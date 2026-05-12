import { defineAsyncComponent } from "vue";
import { defineDashboardWidget } from "@platform/widget-sdk";

export const predictionSummaryPlugin = defineDashboardWidget({
  key: "prediction-summary",
  component: defineAsyncComponent(
    () => import("./PredictionSummaryWidget.vue"),
  ),
  contract: {
    displayName: "Prediction Summary",
    description:
      "Summarizes totals, edited rows, accepted rows, and confidence in prediction review.",
    acceptsProps: [],
    capabilities: {
      reads: ["prediction-grid-items"],
      emits: [],
    },
    selfTests: [
      {
        name: "renders review totals",
        objective:
          "Verify accepted and edited counts reflect injected review grid items.",
        steps: [
          "Provide prediction-grid-items containing accepted and edited items.",
          "Render the widget without additional props.",
        ],
        expected: [
          "Total, Accepted, and Edited values are computed from injected grid items.",
        ],
      },
    ],
  },
});
