import { defineImportPlugin } from "@platform/plugin-sdk"
import ManualDatasetImporter from "./ManualDatasetImporter.vue"

export const importDatasetManualPlugin = defineImportPlugin({
  id: "import-dataset-manual",
  label: "Import from JSON",
  description: "Create a dataset by uploading a JSON file of sample items.",
  icon: "📁",
  surfaces: ["dataset"],
  component: ManualDatasetImporter,
})