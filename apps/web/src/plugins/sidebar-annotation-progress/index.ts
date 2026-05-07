import { defineAsyncComponent } from "vue";
import { defineSidebarPlugin } from "@platform/plugin-sdk";

export const annotationProgressPlugin = defineSidebarPlugin({
  key: "annotation-progress",
  component: defineAsyncComponent(
    () => import("./AnnotationProgressWidget.vue"),
  ),
  contract: {
    displayName: "Annotation Progress",
    description:
      "Shows annotation totals, drafts, selected counts, and label breakdowns.",
    acceptsProps: [
      "chartType",
      "showCounts",
      "showPercent",
      "includeDrafts",
      "showLabelBreakdown",
    ],
    capabilities: {
      reads: ["classify-dashboard"],
      emits: [],
    },
    selfTests: [
      {
        name: "renders dashboard metrics",
        objective:
          "Verify the widget renders shared dashboard stats and selection counts.",
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
