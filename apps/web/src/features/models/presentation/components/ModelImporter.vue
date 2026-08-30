<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { NAlert, NButton, NFormItem, NInput, NSpace, useMessage } from "naive-ui";
import type { ImporterProps } from "@/shared/widgets/sdk";
import { uploadModelApiV1ModelsUploadPost } from "@/generated/orval/endpoints/api";
import { toUserMessage } from "@/shared/api";

const props = defineProps<ImporterProps>();
const { t } = useI18n();
const message = useMessage();
const file = ref<File | null>(null);
const name = ref("");
const loading = ref(false);

function selectFile(event: Event): void {
  const selected = (event.target as HTMLInputElement).files?.[0] ?? null;
  file.value = selected;
  if (selected && !name.value) name.value = selected.name;
}

async function importModel(): Promise<void> {
  if (!file.value || !name.value.trim()) return;
  loading.value = true;
  try {
    await uploadModelApiV1ModelsUploadPost({
      file: file.value,
      metadata: JSON.stringify({
        name: name.value.trim(),
      }),
    });
    message.success(t("models.imported"));
    props.onComplete({ imported: 1, failed: 0 });
  } catch (error) {
    message.error(toUserMessage(error, t("models.importFailed")));
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <NAlert type="info" :show-icon="false">
    {{ t("models.importHelp") }}
  </NAlert>
  <NFormItem :label="t('models.modelFile')" style="margin-top: 12px" required>
    <input type="file" accept=".zip,application/zip" @change="selectFile" />
  </NFormItem>
  <NFormItem :label="t('models.name')" required>
    <NInput v-model:value="name" />
  </NFormItem>
  <NSpace justify="end">
    <NButton @click="props.onCancel()">{{ t("common.cancel") }}</NButton>
    <NButton
      type="primary"
      :disabled="!file || !name.trim()"
      :loading="loading"
      @click="importModel"
    >
      {{ t("common.import") }}
    </NButton>
  </NSpace>
</template>
