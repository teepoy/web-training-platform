import { createDescriptorRegistry } from "@/shared/widgets/sdk";
import "../features/datasets/presentation/dataset-types/classification/registrations";
import "../features/datasets/presentation/dataset-types/sc/registrations";

export const widgetRegistry = createDescriptorRegistry();
