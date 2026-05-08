<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { NButton, NModal, NSpace } from "naive-ui";

import PluginTypeSelector from "./PluginTypeSelector.vue";
import type { PluginCard, PluginKind } from "../plugin-flow";

const props = defineProps<{
  show: boolean;
  plugins: PluginCard[];
  kind: PluginKind;
  title?: string;
  datasetId?: string;
}>();

const emit = defineEmits<{
  "update:show": [value: boolean];
  complete: [result: unknown];
}>();

const step = ref<"select" | "execute">("select");
const selectedPlugin = ref<PluginCard | null>(null);

watch(
  () => props.show,
  (visible) => {
    if (visible) {
      step.value = "select";
      selectedPlugin.value = null;
    }
  },
);

const modalTitle = computed(() => {
  if (step.value === "execute" && selectedPlugin.value) {
    return selectedPlugin.value.label;
  }

  return props.title ?? (props.kind === "import" ? "Import" : props.kind === "export" ? "Export" : "Preview");
});

function handleSelect(plugin: PluginCard): void {
  selectedPlugin.value = plugin;
  step.value = "execute";
}

function handleComplete(result?: unknown): void {
  emit("complete", result);
  emit("update:show", false);
}

function handleCancel(): void {
  if (step.value === "execute") {
    step.value = "select";
    selectedPlugin.value = null;
    return;
  }

  emit("update:show", false);
}

function handleBack(): void {
  step.value = "select";
  selectedPlugin.value = null;
}
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    :title="modalTitle"
    style="max-width: 640px"
    :mask-closable="false"
    @update:show="emit('update:show', $event)"
  >
    <template v-if="step === 'select'">
      <PluginTypeSelector :plugins="plugins" @select="handleSelect" />
    </template>
    <template v-else-if="step === 'execute' && selectedPlugin">
      <component
        :is="selectedPlugin.component"
        v-if="kind === 'import'"
        :dataset-id="datasetId ?? ''"
        :on-complete="handleComplete"
        :on-cancel="handleCancel"
      />
      <component
        :is="selectedPlugin.component"
        v-else-if="kind === 'export'"
        :dataset-id="datasetId ?? ''"
        :on-complete="handleComplete"
        :on-cancel="handleCancel"
      />
      <component
        :is="selectedPlugin.component"
        v-else
        :on-complete="handleComplete"
        :on-cancel="handleCancel"
      />
    </template>
    <template #footer>
      <NSpace justify="space-between">
        <NButton v-if="step === 'execute'" @click="handleBack">
          &larr; Back
        </NButton>
        <span v-else />
        <NButton @click="emit('update:show', false)">
          Cancel
        </NButton>
      </NSpace>
    </template>
  </NModal>
</template>
