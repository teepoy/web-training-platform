import { defineAsyncComponent } from "vue";
import { defineSidebarPlugin } from "@platform/plugin-sdk";

export const interactiveScatterPlugin = defineSidebarPlugin({
  key: "interactive-scatter",
  component: defineAsyncComponent(
    () => import("../../components/interactive-scatter/InteractiveScatterWidget.vue"),
  ),
  contract: {
    displayName: "Interactive Scatter",
    description:
      "Renders metadata-driven scatter points and emits linked sample selection/filter intents.",
    acceptsProps: ["data", "config", "size"],
    capabilities: {
      reads: ["interaction-state"],
      emits: ["select-samples", "apply-filter", "clear-selection"],
    },
    selfTests: [
      {
        name: "point click updates linked sample selection",
        objective:
          "Verify clicking a plotted point emits sample-selection intents for the shared collection.",
        steps: [
          "Render the widget with inline points and config.interaction.collection set.",
          "Click one scatter point.",
        ],
        expected: [
          "The widget emits select-samples for the clicked point.",
          "When filterFromSelection is enabled, the linked sample-viewer can reduce to the selected sample ids.",
        ],
      },
    ],
  },
});
