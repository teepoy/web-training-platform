import { defineAsyncComponent } from "vue";
import { defineImporter } from "@platform/widget-sdk";

export const importParquetPlugin = defineImporter({
  id: "import-parquet",
  label: "Import from Parquet",
  description:
    "Import samples from a HuggingFace-compatible Parquet file (image struct with bytes/path columns).",
  icon: "📦",
  surfaces: ["dataset"],
  component: defineAsyncComponent(() => import("./ParquetImporter.vue")),
});
