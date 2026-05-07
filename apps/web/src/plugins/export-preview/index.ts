import { defineAsyncComponent } from "vue";
import { defineExportPlugin } from "@platform/plugin-sdk";

export const previewExportPlugin = defineExportPlugin({
  id: "export-preview",
  label: "Preview Export",
  description:
    "Generate and inspect dataset export payload without persisting.",
  surfaces: ["dataset"],
  component: defineAsyncComponent(() => import("./PreviewExportPlugin.vue")),
});
