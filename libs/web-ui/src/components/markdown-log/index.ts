import { defineAsyncComponent } from "vue";
import { defineDashboardWidget } from "@platform/widget-sdk";

export const markdownLogPlugin = defineDashboardWidget({
  key: "markdown-log",
  component: defineAsyncComponent(
    () => import("./MarkdownLogWidget.vue"),
  ),
  contract: {
    displayName: "Markdown Log",
    description:
      "Displays log entries or markdown updates in a scrollable widget.",
    acceptsProps: ["data", "config", "size"],
    capabilities: {
      reads: [],
      emits: [],
    },
    selfTests: [
      {
        name: "renders markdown rows",
        objective:
          "Verify one or more markdown entries can be shown without layout errors.",
        steps: [
          "Render the widget with a small list of timestamped log entries.",
        ],
        expected: [
          "The widget renders log content without requiring extra shared context.",
        ],
      },
    ],
  },
});
