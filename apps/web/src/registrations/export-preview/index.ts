import { defineAsyncComponent } from "vue";
import { defineExporter } from "@platform/widget-sdk";

export const previewExportPlugin = defineExporter({
  id: "export-preview",
  label: "Preview Export",
  description:
    "Generate and inspect dataset export payload without persisting.",
  icon: "👁️",
  surfaces: ["dataset"],
  component: defineAsyncComponent(() => import("./PreviewExportPlugin.vue")),
});
