<script setup lang="ts">
import { ref } from "vue";
import { useMessage } from "naive-ui";
import type { ExporterProps } from "@platform/widget-sdk";
import { persistExport } from "@platform/web-ui/api/datasets";

const props = defineProps<ExporterProps>();
const message = useMessage();

const loading = ref(false);
const uri = ref<string | null>(null);

async function runPersist() {
  loading.value = true;
  try {
    const result = await persistExport(props.datasetId);
    uri.value = result.uri;
    message.success(`Export persisted: ${result.uri}`);
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
      <n-alert v-if="uri" type="success" :show-icon="false">
        Persisted URI: {{ uri }}
      </n-alert>
      <n-space justify="end">
        <n-button @click="props.onCancel()">Close</n-button>
        <n-button type="success" :disabled="!uri" @click="done">Done</n-button>
      </n-space>
    </n-space>
  </div>
</template>
