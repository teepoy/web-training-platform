<script setup lang="ts">
import { ref } from "vue";
import { useMessage } from "naive-ui";
import type { ExporterProps } from "@/shared/widgets/sdk";
import { persistExport, buildExportDownloadUrl } from "@/shared/api/datasets";

const props = defineProps<ExporterProps>();
const message = useMessage();

const loading = ref(false);
const uri = ref<string | null>(null);

async function runPersist() {
  loading.value = true;
  try {
    const result = await persistExport(props.datasetId);
    uri.value = result.uri;
    message.success("Export persisted successfully");
  } catch (error) {
    message.error(`Persist failed: ${(error as Error).message}`);
  } finally {
    loading.value = false;
  }
}

function done() {
  props.onComplete({ format: "persist", url: uri.value ?? undefined, message: "Export persisted" });
}
</script>

<template>
  <div>
    <n-space vertical>
      <n-button type="primary" :loading="loading" @click="runPersist">Persist Export</n-button>
      <n-space v-if="uri" vertical :size="4">
        <n-button tag="a" :href="buildExportDownloadUrl(uri)" download type="primary">
          Download Export
        </n-button>
        <n-text depth="3" style="font-size: 11px; word-break: break-all">URI: {{ uri }}</n-text>
      </n-space>
      <n-space justify="end">
        <n-button @click="props.onCancel()">Close</n-button>
        <n-button type="success" :disabled="!uri" @click="done">Done</n-button>
      </n-space>
    </n-space>
  </div>
</template>
