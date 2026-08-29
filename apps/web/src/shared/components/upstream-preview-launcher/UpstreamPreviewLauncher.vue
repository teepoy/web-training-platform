<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { useMessage, NInput, NButton, NSpace, NAlert } from "naive-ui";
import type { PreviewLauncherRequiredProps } from "@/shared/widgets/sdk";
import { createPreviewSession } from "@/shared/api/preview";

const { t } = useI18n();

const props = defineProps<PreviewLauncherRequiredProps>();

const message = useMessage();
const collectionRef = ref("");
const isLoading = ref(false);

async function handlePreview() {
  if (!collectionRef.value.trim()) {
    message.warning(t("widgets.collectionReferenceRequired"));
    return;
  }
  isLoading.value = true;
  try {
    const session = await createPreviewSession(collectionRef.value.trim());
    props.onComplete({ sessionId: session.session_id });
  } catch (err) {
    const error = err instanceof Error ? err.message : t("widgets.previewStartFailed");
    message.error(error);
  } finally {
    isLoading.value = false;
  }
}
</script>

<template>
  <NSpace vertical size="large">
    <NAlert type="info" :title="t('widgets.previewUpstream')">
      {{ t("widgets.previewUpstreamHelp") }}
    </NAlert>

    <NInput
      v-model:value="collectionRef"
      :placeholder="t('widgets.collectionReference')"
      :disabled="isLoading"
      @keyup.enter="handlePreview"
    />

    <NSpace justify="end">
      <NButton :disabled="isLoading" @click="props.onCancel">{{ t("common.cancel") }}</NButton>
      <NButton type="primary" :loading="isLoading" @click="handlePreview">{{
        t("widgets.startPreview")
      }}</NButton>
    </NSpace>
  </NSpace>
</template>
