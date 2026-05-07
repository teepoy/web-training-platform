import { defineAsyncComponent } from "vue";
import { defineImportPlugin } from "@platform/plugin-sdk";

export const importParquetPlugin = defineImportPlugin({
  id: "import-parquet",
  label: "Import from Parquet",
  description:
    "Import samples from a HuggingFace-compatible Parquet file (image struct with bytes/path columns).",
  icon: "📦",
  surfaces: ["dataset"],
  component: defineAsyncComponent(() => import("./ParquetImporter.vue")),
});
