<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { NAlert, NButton, NSpace, useMessage } from "naive-ui";
import type { ExporterProps } from "@/shared/widgets/sdk";
import { exportParquetApiV1PluginsExportParquetExportPost } from "@/generated/orval/endpoints/api";
import { API_BASE } from "@/shared/api/client";
import { downloadAuthenticatedFile } from "@/shared/api/download";
import { toUserMessage } from "@/shared/api";

const props = defineProps<ExporterProps>();
const { t } = useI18n();
const message = useMessage();
const loading = ref(false);

async function exportDataset(): Promise<void> {
  loading.value = true;
  try {
    const result = await exportParquetApiV1PluginsExportParquetExportPost({
      dataset_id: props.datasetId,
    });
    await downloadAuthenticatedFile(
      `${API_BASE}/download?uri=${encodeURIComponent(String(result.uri))}`,
      `${props.datasetId}.parquet`,
    );
    message.success(t("datasetFlows.datasetExported"));
    props.onComplete({ format: "parquet" });
  } catch (error) {
    message.error(toUserMessage(error, t("datasetFlows.datasetExportFailed")));
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <NAlert type="info" :show-icon="false">
    {{ t("datasetFlows.parquetExportHelp") }}
  </NAlert>
  <NSpace justify="end" style="margin-top: 16px">
    <NButton @click="props.onCancel()">{{ t("common.cancel") }}</NButton>
    <NButton type="primary" :loading="loading" @click="exportDataset">
      {{ t("common.export") }}
    </NButton>
  </NSpace>
</template>
