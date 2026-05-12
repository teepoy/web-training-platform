import { defineAsyncComponent } from "vue";
import { defineExporter } from "@platform/widget-sdk";

export const exportParquetPlugin = defineExporter({
  id: "export-parquet",
  label: "Export as Parquet",
  description:
    "Export dataset samples and annotations as a HuggingFace-compatible Parquet file.",
  icon: "📦",
  surfaces: ["dataset"],
  component: defineAsyncComponent(() => import("./ParquetExportPlugin.vue")),
});
