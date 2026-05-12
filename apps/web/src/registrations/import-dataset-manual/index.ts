import { defineImporter } from "@platform/widget-sdk"
import ManualDatasetImporter from "./ManualDatasetImporter.vue"

export const importDatasetManualPlugin = defineImporter({
  id: "import-dataset-manual",
  label: "Import from JSON",
  description: "Create a dataset by uploading a JSON file of sample items.",
  icon: "📁",
  surfaces: ["dataset"],
  component: ManualDatasetImporter,
})
