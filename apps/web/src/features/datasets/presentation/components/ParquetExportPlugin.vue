<script setup lang="ts">
import { ref } from "vue";
import { useMessage } from "naive-ui";
import type { ExporterProps } from "@/shared/widgets/sdk";
import { exportViaCube, buildExportDownloadUrl } from "@/shared/api/datasets";

const props = defineProps<ExporterProps>();
const message = useMessage();

const loading = ref(false);
const uri = ref<string | null>(null);
const rowCount = ref<number | null>(null);

async function runExport() {
  loading.value = true;
  try {
    const result = await exportViaCube("export-parquet", {
      dataset_id: props.datasetId,
    });
    uri.value = (result as Record<string, unknown>).uri as string;
    rowCount.value = ((result as Record<string, unknown>).rows as number) ?? null;
    message.success(`Parquet export complete: ${rowCount.value ?? "?"} rows`);
  } catch (error) {
    message.error(`Parquet export failed: ${(error as Error).message}`);
  } finally {
    loading.value = false;
  }
}

function done() {
  props.onComplete({
    format: "parquet",
    url: uri.value ?? undefined,
    message: `Exported ${rowCount.value ?? "?"} rows as Parquet`,
  });
}
</script>

<template>
  <div>
    <n-space vertical>
      <n-button type="primary" :loading="loading" @click="runExport">
        Export as Parquet
      </n-button>

      <n-space v-if="uri" vertical :size="4">
        <template v-if="rowCount !== null">
          <n-text>{{ rowCount }} rows exported</n-text>
        </template>
        <n-button tag="a" :href="buildExportDownloadUrl(uri)" download type="primary">
          Download Parquet
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
