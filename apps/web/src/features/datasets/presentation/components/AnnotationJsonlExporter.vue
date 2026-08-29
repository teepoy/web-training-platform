<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { NAlert, NButton, NSpace, useMessage } from "naive-ui";
import type { ExporterProps } from "@/shared/widgets/sdk";
import { API_BASE } from "@/shared/api/client";
import { downloadAuthenticatedFile } from "@/shared/api/download";
import { toUserMessage } from "@/shared/api";

const props = defineProps<ExporterProps>();
const { t } = useI18n();
const message = useMessage();
const loading = ref(false);

async function exportAnnotations(): Promise<void> {
  loading.value = true;
  try {
    await downloadAuthenticatedFile(
      `${API_BASE}/datasets/${encodeURIComponent(props.datasetId)}/annotations/export`,
      `${props.datasetId}-annotations.jsonl`,
    );
    message.success(t("datasetFlows.annotationsExported"));
    props.onComplete({ format: "jsonl" });
  } catch (error) {
    message.error(toUserMessage(error, t("datasetFlows.annotationExportFailed")));
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <NAlert type="info" :show-icon="false">
    {{ t("datasetFlows.annotationExportHelp") }}
  </NAlert>
  <NSpace justify="end" style="margin-top: 16px">
    <NButton @click="props.onCancel()">{{ t("common.cancel") }}</NButton>
    <NButton type="primary" :loading="loading" @click="exportAnnotations">
      {{ t("common.export") }}
    </NButton>
  </NSpace>
</template>
