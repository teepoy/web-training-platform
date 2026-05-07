import { defineAsyncComponent } from "vue";
import { defineExportPlugin } from "@platform/plugin-sdk";

export const exportParquetPlugin = defineExportPlugin({
  id: "export-parquet",
  label: "Export as Parquet",
  description:
    "Export dataset samples and annotations as a HuggingFace-compatible Parquet file.",
  icon: "📦",
  surfaces: ["dataset"],
  component: defineAsyncComponent(() => import("./ParquetExportPlugin.vue")),
});
