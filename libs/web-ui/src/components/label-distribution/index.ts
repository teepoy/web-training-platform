import { defineAsyncComponent } from "vue";
import { defineDashboardWidget } from "@platform/widget-sdk";

export const labelDistributionPlugin = defineDashboardWidget({
  key: "label-distribution",
  component: defineAsyncComponent(
    () => import("./LabelDistributionWidget.vue"),
  ),
  contract: {
    displayName: "Label Distribution",
    description:
      "Displays label counts and supports click-to-filter for the classify surface.",
    acceptsProps: ["orientation", "showValues", "maxBars"],
    capabilities: {
      reads: ["classify-dashboard", "interaction-state"],
      emits: ["select-labels", "clear-selection"],
    },
    selfTests: [
      {
        name: "renders sorted labels",
        objective:
          "Verify label counts render and overflow labels can be grouped.",
        steps: [
          "Provide more labels than maxBars in the shared dashboard stats.",
          "Render the widget in horizontal orientation.",
        ],
        expected: [
          "The widget renders without errors.",
          "The chart can group remaining labels into an Other bucket.",
        ],
      },
      {
        name: "click to filter",
        objective:
          "Verify a chart click can update the shared label filter state.",
        steps: [
          "Provide a shared interaction-state with no activeLabelFilter.",
          "Click a concrete label bar in the chart.",
        ],
        expected: [
          "The widget emits a select-labels intent through the shared interaction context.",
          "The active label is visually emphasized once the interaction state updates.",
        ],
      },
    ],
  },
});
