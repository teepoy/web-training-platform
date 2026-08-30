<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { useMessage } from "naive-ui";
import type { ImporterProps } from "@/shared/widgets/sdk";
import { importParquetApiV1PluginsImportParquetImportPost } from "@/generated/orval/endpoints/api";
import { toUserMessage } from "@/shared/api";

const props = defineProps<ImporterProps>();
const message = useMessage();
const { t } = useI18n();

const file = ref<File | null>(null);
const loading = ref(false);
const result = ref<{ imported: number; failed: number; errors: string[] } | null>(null);

function onFileChange(e: Event) {
  const target = e.target as HTMLInputElement;
  file.value = target.files?.[0] ?? null;
  result.value = null;
}

async function submit() {
  if (!file.value) {
    message.error(t("datasetFlows.parquetRequired"));
    return;
  }

  loading.value = true;
  try {
    const data = await importParquetApiV1PluginsImportParquetImportPost(
      { file: file.value as File },
      { dataset_id: props.datasetId },
    );
    result.value = {
      imported: data.imported,
      failed: data.failed,
      errors: data.errors ?? [],
    };
    message.success(t("datasetFlows.samplesImported", { count: data.imported }));
    props.onComplete({
      imported: data.imported,
      failed: data.failed,
      message: data.errors?.length
        ? t("datasetFlows.parquetImportWarnings", { warnings: data.errors.join("; ") })
        : t("datasetFlows.parquetImportComplete"),
    });
  } catch (error) {
    message.error(toUserMessage(error, t("datasetFlows.parquetImportFailed")));
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div>
    <n-space vertical>
      <n-form-item :label="t('datasetFlows.parquetFile')">
        <input type="file" accept=".parquet,application/octet-stream" @change="onFileChange" />
      </n-form-item>

      <n-alert v-if="file" type="info" :show-icon="false">
        {{ file.name }} ({{
          t("datasetFlows.fileSizeKb", { size: (file.size / 1024).toFixed(1) })
        }})
      </n-alert>

      <n-alert v-if="result" type="success" :show-icon="false">
        {{ t("datasetFlows.samplesImported", { count: result.imported }) }}
        <span v-if="result.failed > 0">
          , {{ t("datasetFlows.samplesFailed", { count: result.failed }) }}
        </span>
        <ul
          v-if="result.errors.length"
          style="margin: 4px 0 0; padding-left: 20px; font-size: 12px"
        >
          <li v-for="w in result.errors" :key="w">{{ w }}</li>
        </ul>
      </n-alert>

      <n-space justify="end">
        <n-button @click="props.onCancel()">{{ t("common.cancel") }}</n-button>
        <n-button type="primary" :loading="loading" :disabled="!file" @click="submit">
          {{ t("common.import") }}
        </n-button>
      </n-space>
    </n-space>
  </div>
</template>
