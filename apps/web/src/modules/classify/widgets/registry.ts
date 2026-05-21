import { createDescriptorRegistry } from "@/shared/widgets/sdk";
import { classifyWidgetDescriptors } from "./descriptors";

export const classifyWidgetRegistry = createDescriptorRegistry();

for (const descriptor of classifyWidgetDescriptors) {
  classifyWidgetRegistry.registerWidget(descriptor);
}

export function getClassifyWidgetCount(): number {
  return classifyWidgetRegistry.getAllWidgets().length;
}
