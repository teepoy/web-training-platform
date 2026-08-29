import { createDescriptorRegistry } from "@/shared/widgets/sdk";
import "../features/datasets/presentation/dataset-types/classification/registrations";
import "../features/datasets/presentation/dataset-types/sc/registrations";
import { scPredictionExporter } from "@/features/sc/presentation/registrations/predictionExport";
import {
  datasetExporters,
  datasetImporters,
} from "@/features/datasets/presentation/registrations/transfers";
import {
  modelExporter,
  modelImporter,
} from "@/features/models/presentation/registrations/transfers";

export const widgetRegistry = createDescriptorRegistry();
widgetRegistry.registerExporter(scPredictionExporter);
for (const importer of [...datasetImporters, modelImporter]) {
  widgetRegistry.registerImporter(importer);
}
for (const exporter of [...datasetExporters, modelExporter]) {
  widgetRegistry.registerExporter(exporter);
}
