import { createDescriptorRegistry } from "@/shared/widgets/sdk";
import "../features/datasets/presentation/dataset-types/classification/registrations";
import "../features/datasets/presentation/dataset-types/sc/registrations";
import { scPredictionExporter } from "@/features/sc/presentation/registrations/predictionExport";

export const widgetRegistry = createDescriptorRegistry();
widgetRegistry.registerExporter(scPredictionExporter);
