<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { NAlert, NButton, NSpace, useMessage } from "naive-ui";
import type { ExporterProps } from "@/shared/widgets/sdk";
import { getDownloadModelApiV1ModelsModelIdDownloadGetUrl } from "@/generated/orval/endpoints/api";
import { downloadAuthenticatedFile } from "@/shared/api/download";
import { toUserMessage } from "@/shared/api";

const props = defineProps<ExporterProps>();
const { t } = useI18n();
const message = useMessage();
const loading = ref(false);

async function exportModel(): Promise<void> {
  const modelId = props.resourceId;
  if (!modelId) return;
  loading.value = true;
  try {
    await downloadAuthenticatedFile(
      getDownloadModelApiV1ModelsModelIdDownloadGetUrl(modelId, { portable: true }),
      `${modelId}.model-package.zip`,
    );
    message.success(t("models.exported"));
    props.onComplete({ format: "model-package" });
  } catch (error) {
    message.error(toUserMessage(error, t("models.exportFailed")));
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <NAlert type="info" :show-icon="false">{{ t("models.exportHelp") }}</NAlert>
  <NSpace justify="end" style="margin-top: 16px">
    <NButton @click="props.onCancel()">{{ t("common.cancel") }}</NButton>
    <NButton type="primary" :disabled="!props.resourceId" :loading="loading" @click="exportModel">
      {{ t("common.export") }}
    </NButton>
  </NSpace>
</template>
