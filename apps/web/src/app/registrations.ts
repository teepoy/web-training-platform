import { createDescriptorRegistry } from "@/shared/widgets/sdk";
import { classifyWidgetDescriptors } from "../features/classify/presentation/widgets/descriptors";
import "../modules/dataset-classification/registrations";
import "../modules/dataset-detection/registrations";
import "../modules/dataset-vqa/registrations";

export const widgetRegistry = createDescriptorRegistry();

for (const descriptor of classifyWidgetDescriptors) {
  widgetRegistry.registerWidget(descriptor);
}
