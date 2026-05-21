import { createDescriptorRegistry } from "@/shared/widgets/sdk";
import { classifyWidgetDescriptors } from "../features/classify/presentation/widgets/descriptors";

export const widgetRegistry = createDescriptorRegistry();

for (const descriptor of classifyWidgetDescriptors) {
  widgetRegistry.registerWidget(descriptor);
}
