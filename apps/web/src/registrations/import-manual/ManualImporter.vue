<script setup lang="ts">
import { ref, watch } from "vue";
import { useMessage, type FormInst, type FormRules } from "naive-ui";
import type { ImporterProps } from "@platform/widget-sdk";
import { api } from "../../api";

const props = defineProps<ImporterProps>();
const message = useMessage();

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
        message.error("Metadata must be valid JSON");
        return;
      }
    }

    const imageUris = form.value.image_uris
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);

    loading.value = true;
    try {
      const sample = await api.createSample(props.datasetId, {
        image_uris: imageUris,
        metadata,
      });

      if (uploadFile.value) {
        await api.uploadSampleImage(sample.id, uploadFile.value);
      }

      message.success("Sample created");
      resetLocalState();
      props.onComplete({ imported: 1, failed: 0, message: "Manual import complete" });
    } catch (error) {
      message.error(`Failed to create sample: ${(error as Error).message}`);
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
    <n-form-item label="Image URIs (comma-separated, optional)" path="image_uris">
      <n-input
        v-model:value="form.image_uris"
        placeholder="e.g. s3://bucket/img1.jpg, s3://bucket/img2.jpg"
      />
    </n-form-item>

    <n-form-item label="Upload Image (optional)">
      <div>
        <input
          ref="fileInputRef"
          type="file"
          accept="image/*"
          style="display: none"
          @change="onFileChange"
        />
        <n-button @click="(fileInputRef as HTMLInputElement | null)?.click()">
          Choose Image
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

    <n-form-item label="Metadata (JSON)" path="metadata_raw">
      <n-input
        v-model:value="form.metadata_raw"
        type="textarea"
        placeholder='{"key": "value"}'
        :autosize="{ minRows: 3, maxRows: 6 }"
      />
    </n-form-item>
  </n-form>

  <div style="display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px">
    <n-button @click="props.onCancel()">Cancel</n-button>
    <n-button type="primary" :loading="loading" @click="submit">Create</n-button>
  </div>
</template>
