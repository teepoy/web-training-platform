<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { NAlert, NButton, NFormItem, NSpace, useMessage } from "naive-ui";
import type { ImporterProps } from "@/shared/widgets/sdk";
import { importAnnotationsApiV1DatasetsDatasetIdAnnotationsImportPost } from "@/generated/orval/endpoints/api";
import { toUserMessage } from "@/shared/api";

const props = defineProps<ImporterProps>();
const { t } = useI18n();
const message = useMessage();
const file = ref<File | null>(null);
const loading = ref(false);

function selectFile(event: Event): void {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null;
}

async function importAnnotations(): Promise<void> {
  if (!file.value) return;
  loading.value = true;
  try {
    const result = await importAnnotationsApiV1DatasetsDatasetIdAnnotationsImportPost(
      props.datasetId,
      { file: file.value },
    );
    message.success(
      t("datasetFlows.annotationsImported", {
        imported: result.imported,
        cleared: result.cleared,
      }),
    );
    props.onComplete({ imported: result.imported, failed: 0 });
  } catch (error) {
    message.error(toUserMessage(error, t("datasetFlows.annotationImportFailed")));
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <NAlert type="info" :show-icon="false">
    {{ t("datasetFlows.annotationImportHelp") }}
  </NAlert>
  <NFormItem :label="t('datasetFlows.annotationFile')" style="margin-top: 12px">
    <input type="file" accept=".jsonl,application/x-ndjson" @change="selectFile" />
  </NFormItem>
  <NSpace justify="end">
    <NButton @click="props.onCancel()">{{ t("common.cancel") }}</NButton>
    <NButton type="primary" :disabled="!file" :loading="loading" @click="importAnnotations">
      {{ t("common.import") }}
    </NButton>
  </NSpace>
</template>
