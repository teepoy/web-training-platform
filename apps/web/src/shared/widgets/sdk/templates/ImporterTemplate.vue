<!--
  ImporterTemplate.vue
  ────────────────────────
  Copy this as apps/web/src/registrations/import-<your-id>/<YourImporter>.vue

  The host view mounts this inside a modal and passes these props:
    datasetId  — target dataset / preview session ID
    onComplete — call when import finishes (host refreshes data and closes modal)
    onCancel   — call when user cancels (host closes modal)

  After creating the component, export its descriptor in index.ts
  (see ImporterIndexTemplate.ts) and register it in
  apps/web/src/registrations/index.ts.
-->
<script setup lang="ts">
import type { ImporterProps } from "@/shared/widgets/sdk";

const props = defineProps<ImporterProps>();

async function doImport() {
  // Call your backend or an existing API client helper here.
  // Example: api.importSamples(props.datasetId, items)

  props.onComplete({ imported: 0, failed: 0 });
}
</script>

<template>
  <div>
    <p>Importing into dataset {{ props.datasetId }}</p>
    <button @click="doImport">Start Import</button>
    <button @click="props.onCancel()">Cancel</button>
  </div>
</template>
