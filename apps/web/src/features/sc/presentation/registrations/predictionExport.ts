import { defineAsyncComponent } from "vue";
import { defineExporter } from "@/shared/widgets/sdk";

export const scPredictionExporter = defineExporter({
  id: "sc-prediction-results-v1",
  label: "Export current results",
  description: "Export current SC predictions as KLARF, Parquet, or a ZIP package.",
  icon: "⇩",
  surfaces: ["prediction"],
  component: defineAsyncComponent(() => import("../components/ScPredictionExportPlugin.vue")),
});
