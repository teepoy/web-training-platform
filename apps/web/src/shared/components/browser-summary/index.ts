import { defineAsyncComponent } from "vue";
import { defineDashboardWidget } from "@/shared/widgets/sdk";

export const browserSummaryPlugin = defineDashboardWidget({
  key: "browser-summary",
  component: defineAsyncComponent(
    () => import("./BrowserSummaryWidget.vue"),
  ),
  contract: {
    displayName: "Browser Summary",
    description:
      "Compact read-only widget showing loaded item count, visible (filtered) count, and active filter label.",
    acceptsProps: ["totalLoaded", "filteredCount"],
    capabilities: {
      reads: ["browser-dashboard"],
      emits: [],
    },
    selfTests: [
      {
        name: "renders item counts",
        objective:
          "Verify the widget shows loaded and filtered counts from injected browser dashboard context.",
        steps: [
          "Provide browser-dashboard context with totalLoaded and filteredCount values.",
          "Render the widget without additional props.",
        ],
        expected: [
          "The widget displays 'Showing X of Y items' without errors.",
          "When context is absent the widget degrades gracefully showing '—'.",
        ],
      },
    ],
  },
});
