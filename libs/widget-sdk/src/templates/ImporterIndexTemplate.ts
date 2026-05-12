/**
 * ImporterIndexTemplate.ts
 * ────────────────────────────
 * Copy this as apps/web/src/registrations/import-<your-id>/index.ts
 */

import { defineAsyncComponent } from "vue";
import { defineImporter } from "@platform/widget-sdk";

export const myImporterPlugin = defineImporter({
  id: "my-importer",
  label: "My Importer",
  description: "Import data from My Source.",
  surfaces: ["dataset"], // which surfaces show this importer
  component: defineAsyncComponent(() => import("./MyImporter.vue")),
});
