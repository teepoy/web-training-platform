import { createDescriptorRegistry } from "@/shared/widgets/sdk";
import { classifyWidgetDescriptors } from "../features/classify/presentation/widgets/descriptors";
import "../features/datasets/presentation/dataset-types/classification/registrations";
import "../features/datasets/presentation/dataset-types/detection/registrations";
import "../features/datasets/presentation/dataset-types/vqa/registrations";
import "../features/datasets/presentation/dataset-types/sc/registrations";

export const widgetRegistry = createDescriptorRegistry();

for (const descriptor of classifyWidgetDescriptors) {
  widgetRegistry.registerWidget(descriptor);
}
