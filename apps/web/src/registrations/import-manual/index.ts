import { defineAsyncComponent } from "vue";
import { defineImporter } from "@platform/widget-sdk";

export const manualImportPlugin = defineImporter({
  id: "import-manual",
  label: "Manual Sample Entry",
  description:
    "Create one sample at a time with URI, metadata, or uploaded image.",
  icon: "✏️",
  surfaces: ["dataset"],
  component: defineAsyncComponent(() => import("./ManualImporter.vue")),
});
