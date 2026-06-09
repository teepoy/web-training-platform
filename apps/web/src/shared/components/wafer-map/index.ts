import { defineAsyncComponent } from "vue";
import { defineDashboardWidget } from "@/shared/widgets/sdk";

export const waferMapPlugin = defineDashboardWidget({
  key: "wafer-map",
  component: defineAsyncComponent(
    () => import("./WaferMapWidget.vue"),
  ),
  contract: {
    displayName: "Wafer Map",
    description:
      "Native Canvas wafer scatter map with spatial selection. Renders wafer-scale point data with class-color coding and emits linked sample selection intents via the data pipeline.",
    acceptsProps: ["data", "config", "size"],
    capabilities: {
      reads: ["interaction-state"],
      emits: ["select-samples"],
    },
    selfTests: [],
  },
});
