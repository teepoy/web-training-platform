import { createDescriptorRegistry } from "@/shared/widgets/sdk";
import { classifyWidgetDescriptors } from "../modules/classify/widgets/descriptors";

export const widgetRegistry = createDescriptorRegistry();

for (const descriptor of classifyWidgetDescriptors) {
  widgetRegistry.registerWidget(descriptor);
}
