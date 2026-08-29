import { defineAsyncComponent } from "vue";
import { defineExporter } from "@/shared/widgets/sdk";

export const scPredictionExporter = defineExporter({
  id: "sc-prediction-results-v1",
  label: "Export current results",
  labelKey: "sc.exportResults",
  description: "Export current SC predictions as KLARF, Parquet, or a ZIP package.",
  descriptionKey: "sc.predictionExporterHelp",
  icon: "⇩",
  surfaces: ["prediction"],
  component: defineAsyncComponent(() => import("../components/PredictionExportPlugin.vue")),
});
