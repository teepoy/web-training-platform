<script setup lang="ts">
import { ref } from "vue";
import { NButton, NH2, NSpace } from "naive-ui";

import PluginFlowModal from "../../plugin-flow-modal/PluginFlowModal.vue";
import type { PluginCard } from "../../../plugin-flow";

const props = withDefaults(
  defineProps<{
    importerPlugins: PluginCard[];
    previewLauncherPlugins: PluginCard[];
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

    <PluginFlowModal
      v-model:show="showImportFlow"
      :plugins="props.importerPlugins"
      kind="import"
      title="Import Dataset"
      @complete="handleImportComplete"
    />

    <PluginFlowModal
      v-model:show="showPreviewFlow"
      :plugins="props.previewLauncherPlugins"
      kind="preview"
      title="Preview Dataset"
      @complete="handlePreviewComplete"
    />
  </div>
</template>
