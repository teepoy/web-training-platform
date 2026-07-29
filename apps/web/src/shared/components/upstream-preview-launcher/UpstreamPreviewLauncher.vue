<script setup lang="ts">
import { ref } from "vue";
import { useMessage, NInput, NButton, NSpace, NAlert } from "naive-ui";
import type { PreviewLauncherRequiredProps } from "@/shared/widgets/sdk";
import { createPreviewSession } from "@/shared/api/preview";

const props = defineProps<PreviewLauncherRequiredProps>();

const message = useMessage();
const collectionRef = ref("");
const isLoading = ref(false);

async function handlePreview() {
  if (!collectionRef.value.trim()) {
    message.warning("Please enter a collection ref");
    return;
  }
  isLoading.value = true;
  try {
    const session = await createPreviewSession(collectionRef.value.trim());
    props.onComplete({ sessionId: session.session_id });
  } catch (err) {
    const error = err instanceof Error ? err.message : "Failed to start preview";
    message.error(error);
  } finally {
    isLoading.value = false;
  }
}
</script>

<template>
  <NSpace vertical size="large">
    <NAlert type="info" title="Preview upstream collection">
      Enter a collection reference to preview remote items before importing them.
    </NAlert>

    <NInput
      v-model:value="collectionRef"
      placeholder="s3://bucket/path or upstream collection id"
      :disabled="isLoading"
      @keyup.enter="handlePreview"
    />

    <NSpace justify="end">
      <NButton :disabled="isLoading" @click="props.onCancel"> Cancel </NButton>
      <NButton type="primary" :loading="isLoading" @click="handlePreview"> Start Preview </NButton>
    </NSpace>
  </NSpace>
</template>
