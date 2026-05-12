import { defineAsyncComponent } from "vue";
import { defineExporter } from "@platform/widget-sdk";

export const persistExportPlugin = defineExporter({
  id: "export-persist",
  label: "Persist Export",
  description: "Persist dataset export artifact and return a URI.",
  icon: "💾",
  surfaces: ["dataset"],
  component: defineAsyncComponent(() => import("./PersistExportPlugin.vue")),
});
