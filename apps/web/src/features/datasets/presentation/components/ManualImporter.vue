<script setup lang="ts">
import { ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useMessage, type FormInst, type FormRules } from "naive-ui";
import type { ImporterProps } from "@/shared/widgets/sdk";
import {
  createSampleApiV1DatasetsDatasetIdSamplesPost,
  uploadSampleImageApiV1DatasetsDatasetIdSamplesSampleIdUploadPost,
} from "@/generated/orval/endpoints/api";
import { toUserMessage } from "@/shared/api";

const props = defineProps<ImporterProps>();
const message = useMessage();
const { t } = useI18n();

const formRef = ref<FormInst | null>(null);
const form = ref({ image_uris: "", metadata_raw: "" });
const rules: FormRules = {
  image_uris: [],
};

const uploadFile = ref<File | null>(null);
const uploadPreviewUrl = ref<string | null>(null);
const loading = ref(false);
const fileInputRef = ref<HTMLInputElement | null>(null);

function onFileChange(e: Event) {
  const target = e.target as HTMLInputElement;
  const file = target.files?.[0] ?? null;
  uploadFile.value = file;
  if (uploadPreviewUrl.value) {
    URL.revokeObjectURL(uploadPreviewUrl.value);
    uploadPreviewUrl.value = null;
  }
  if (file) {
    uploadPreviewUrl.value = URL.createObjectURL(file);
  }
}

function resetLocalState() {
  form.value = { image_uris: "", metadata_raw: "" };
  uploadFile.value = null;
  if (uploadPreviewUrl.value) {
    URL.revokeObjectURL(uploadPreviewUrl.value);
  }
  uploadPreviewUrl.value = null;
}

function submit() {
  formRef.value?.validate(async (errors) => {
    if (errors) return;

    let metadata: Record<string, unknown> = {};
    if (form.value.metadata_raw.trim()) {
      try {
        metadata = JSON.parse(form.value.metadata_raw) as Record<string, unknown>;
      } catch {
        message.error(t("datasetFlows.metadataJsonInvalid"));
        return;
      }
    }

    const imageUris = form.value.image_uris
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);

    loading.value = true;
    try {
      const sample = await createSampleApiV1DatasetsDatasetIdSamplesPost(props.datasetId, {
        image_uris: imageUris,
        metadata,
      });

      if (uploadFile.value) {
        await uploadSampleImageApiV1DatasetsDatasetIdSamplesSampleIdUploadPost(
          props.datasetId,
          sample.id!,
          { file: uploadFile.value },
        );
      }

      message.success(t("datasetFlows.sampleCreated"));
      resetLocalState();
      props.onComplete({ imported: 1, failed: 0, message: t("datasetFlows.manualComplete") });
    } catch (error) {
      message.error(toUserMessage(error, t("datasetFlows.sampleCreateFailed")));
    } finally {
      loading.value = false;
    }
  });
}

watch(
  () => props.datasetId,
  () => {
    resetLocalState();
  },
);
</script>

<template>
  <n-form ref="formRef" :model="form" :rules="rules" label-placement="top">
    <n-form-item :label="t('datasetFlows.imageUris')" path="image_uris">
      <n-input
        v-model:value="form.image_uris"
        placeholder="e.g. s3://bucket/img1.jpg, s3://bucket/img2.jpg"
      />
    </n-form-item>

    <n-form-item :label="t('datasetFlows.uploadImage')">
      <div>
        <input
          ref="fileInputRef"
          type="file"
          accept="image/*"
          style="display: none"
          @change="onFileChange"
        />
        <n-button @click="(fileInputRef as HTMLInputElement | null)?.click()">
          {{ t("datasetFlows.chooseImage") }}
        </n-button>
        <n-image
          v-if="uploadPreviewUrl"
          :src="uploadPreviewUrl"
          width="80"
          height="80"
          object-fit="cover"
          style="margin-top: 8px; border-radius: 4px"
        />
      </div>
    </n-form-item>

    <n-form-item :label="t('datasetFlows.metadataJson')" path="metadata_raw">
      <n-input
        v-model:value="form.metadata_raw"
        type="textarea"
        placeholder='{"key": "value"}'
        :autosize="{ minRows: 3, maxRows: 6 }"
      />
    </n-form-item>
  </n-form>

  <div style="display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px">
    <n-button @click="props.onCancel()">{{ t("common.cancel") }}</n-button>
    <n-button type="primary" :loading="loading" @click="submit">{{ t("common.create") }}</n-button>
  </div>
</template>
