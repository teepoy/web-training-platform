import { defineAsyncComponent } from "vue";
import { defineImportPlugin } from "@platform/plugin-sdk";

export const manualImportPlugin = defineImportPlugin({
  id: "import-manual",
  label: "Manual Sample Entry",
  description:
    "Create one sample at a time with URI, metadata, or uploaded image.",
  surfaces: ["dataset"],
  component: defineAsyncComponent(() => import("./ManualImporter.vue")),
});
