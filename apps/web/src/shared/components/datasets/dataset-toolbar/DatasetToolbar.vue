<script setup lang="ts">
import { ref } from "vue";
import { NButton, NH2, NSpace } from "naive-ui";

import FlowModal from "../../flow-modal/FlowModal.vue";
import type { FlowCard } from "../../../flow";

const props = withDefaults(
  defineProps<{
    importerFlows: FlowCard[];
    previewLauncherFlows: FlowCard[];
    title?: string;
  }>(),
  {
    title: "Datasets",
  },
);

const emit = defineEmits<{
  "import-complete": [];
  "preview-complete": [result: unknown];
}>();

const showImportFlow = ref(false);
const showPreviewFlow = ref(false);

function handleImportComplete(): void {
  showImportFlow.value = false;
  emit("import-complete");
}

function handlePreviewComplete(result: unknown): void {
  showPreviewFlow.value = false;
  emit("preview-complete", result);
}
</script>

<template>
  <div>
    <n-space justify="space-between" align="center" style="margin-bottom: 16px">
      <n-h2 style="margin: 0">{{ props.title }}</n-h2>
      <n-space>
        <n-button @click="showImportFlow = true">
          Import Dataset
        </n-button>
        <n-button type="primary" @click="showPreviewFlow = true">
          Preview Dataset
        </n-button>
      </n-space>
    </n-space>

    <FlowModal
      v-model:show="showImportFlow"
      :flows="props.importerFlows"
      kind="import"
      title="Import Dataset"
      @complete="handleImportComplete"
    />

    <FlowModal
      v-model:show="showPreviewFlow"
      :flows="props.previewLauncherFlows"
      kind="preview"
      title="Preview Dataset"
      @complete="handlePreviewComplete"
    />
  </div>
</template>
