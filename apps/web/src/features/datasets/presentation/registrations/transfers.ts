import { defineAsyncComponent } from "vue";
import { defineExporter, defineImporter } from "@/shared/widgets/sdk";

export const datasetImporters = [
  defineImporter({
    id: "dataset-sample-manual-v1",
    label: "Manual sample",
    labelKey: "datasetDetail.manualEntry",
    description: "Add one sample.",
    descriptionKey: "datasetDetail.manualEntryHelp",
    icon: "✏️",
    surfaces: ["dataset"],
    component: defineAsyncComponent(() => import("../components/ManualImporter.vue")),
  }),
  defineImporter({
    id: "dataset-json-v1",
    label: "JSON samples",
    labelKey: "datasetDetail.importJson",
    description: "Import sample rows from JSON.",
    descriptionKey: "datasetDetail.importJsonHelp",
    icon: "📁",
    surfaces: ["dataset"],
    component: defineAsyncComponent(() => import("../components/ManualDatasetImporter.vue")),
  }),
  defineImporter({
    id: "dataset-parquet-v1",
    label: "Parquet dataset",
    labelKey: "datasetDetail.importParquet",
    description: "Import portable Parquet sample rows.",
    descriptionKey: "datasetDetail.importParquetHelp",
    icon: "📦",
    surfaces: ["dataset"],
    component: defineAsyncComponent(() => import("../components/ParquetImporter.vue")),
  }),
  defineImporter({
    id: "annotation-jsonl-v1",
    label: "Annotation JSONL",
    labelKey: "datasetFlows.annotationJsonl",
    description: "Replace provided annotations by platform sample ID.",
    descriptionKey: "datasetFlows.annotationImportHelp",
    icon: "🏷️",
    surfaces: ["annotation"],
    component: defineAsyncComponent(() => import("../components/AnnotationJsonlImporter.vue")),
  }),
];

export const datasetExporters = [
  defineExporter({
    id: "dataset-parquet-v1",
    label: "Parquet dataset",
    labelKey: "datasetFlows.parquetDataset",
    description: "Export samples and latest labels as portable Parquet.",
    descriptionKey: "datasetFlows.parquetExportHelp",
    icon: "📦",
    surfaces: ["dataset"],
    component: defineAsyncComponent(() => import("../components/DatasetParquetExporter.vue")),
  }),
  defineExporter({
    id: "annotation-jsonl-v1",
    label: "Annotation JSONL",
    labelKey: "datasetFlows.annotationJsonl",
    description: "Export latest annotations keyed by platform sample ID.",
    descriptionKey: "datasetFlows.annotationExportHelp",
    icon: "🏷️",
    surfaces: ["annotation"],
    component: defineAsyncComponent(() => import("../components/AnnotationJsonlExporter.vue")),
  }),
];
