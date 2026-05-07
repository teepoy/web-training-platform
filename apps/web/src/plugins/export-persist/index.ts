import { defineAsyncComponent } from "vue";
import { defineExportPlugin } from "@platform/plugin-sdk";

export const persistExportPlugin = defineExportPlugin({
  id: "export-persist",
  label: "Persist Export",
  description: "Persist dataset export artifact and return a URI.",
  surfaces: ["dataset"],
  component: defineAsyncComponent(() => import("./PersistExportPlugin.vue")),
});
