import { defineAsyncComponent } from "vue";
import { defineSidebarPlugin } from "@platform/plugin-sdk";

export const waferMapPlugin = defineSidebarPlugin({
  key: "wafer-map",
  component: defineAsyncComponent(
    () => import("../../components/wafer-map/WaferMapWidget.vue"),
  ),
  contract: {
    displayName: "Wafer Map",
    description:
      "Renders high-density wafer scatter points and emits linked selection/filter intents.",
    acceptsProps: ["data", "config", "size"],
    capabilities: {
      reads: ["interaction-state"],
      emits: [
        "select-samples",
        "select-predictions",
        "apply-filter",
        "clear-selection",
      ],
    },
    selfTests: [
      {
        name: "brush updates linked collection",
        objective:
          "Verify brush selection emits collection-scoped intents so linked tables can filter.",
        steps: [
          "Render the widget with inline points and config.interaction.collection set.",
          "Brush-select a point subset in the wafer map.",
        ],
        expected: [
          "The widget emits select-* and apply-filter intents with metadata.collection.",
          "A linked data-table widget on the same collection can reduce to selected rows.",
        ],
      },
    ],
  },
});
