<script setup lang="ts">
import { computed, ref } from "vue";
import { useMessage } from "naive-ui";
import type { ExportPluginRequiredProps } from "@platform/plugin-sdk";
import { api } from "../../api";

const props = defineProps<ExportPluginRequiredProps>();
const message = useMessage();

const loading = ref(false);
const exportData = ref<Record<string, unknown> | null>(null);

const exportJson = computed(() =>
  exportData.value ? JSON.stringify(exportData.value, null, 2) : "",
);

async function runPreview() {
  loading.value = true;
  try {
    const result = await api.getExport(props.datasetId);
    exportData.value = result as unknown as Record<string, unknown>;
  } catch (error) {
    message.error(`Export preview failed: ${(error as Error).message}`);
  } finally {
    loading.value = false;
  }
}

function close() {
  props.onComplete({ format: "preview", message: "Export preview complete" });
}
</script>

<template>
  <div>
    <div style="display: flex; justify-content: space-between; gap: 8px; margin-bottom: 12px">
      <n-button type="primary" :loading="loading" @click="runPreview">Run Preview</n-button>
      <n-button @click="props.onCancel()">Close</n-button>
    </div>

    <n-card v-if="exportData" title="Export Preview" size="small">
      <n-scrollbar style="max-height: 420px">
        <pre style="margin: 0; font-size: 12px; white-space: pre-wrap; word-break: break-all">{{ exportJson }}</pre>
      </n-scrollbar>
      <div style="display: flex; justify-content: flex-end; margin-top: 10px">
        <n-button type="success" @click="close">Done</n-button>
      </div>
    </n-card>

    <n-empty v-else description="Run preview to load export data." style="margin-top: 16px" />
  </div>
</template>
