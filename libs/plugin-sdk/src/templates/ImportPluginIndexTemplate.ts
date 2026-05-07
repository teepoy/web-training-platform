/**
 * ImportPluginIndexTemplate.ts
 * ────────────────────────────
 * Copy this as apps/web/src/plugins/import-<your-id>/index.ts
 */

import { defineAsyncComponent } from "vue";
import { defineImportPlugin } from "@platform/plugin-sdk";

export const myImporterPlugin = defineImportPlugin({
  id: "my-importer",
  label: "My Importer",
  description: "Import data from My Source.",
  surfaces: ["dataset"], // which surfaces show this importer
  component: defineAsyncComponent(() => import("./MyImporter.vue")),
});
