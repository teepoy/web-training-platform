<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { NButton, NModal, NSpace } from "naive-ui";

import FlowTypeSelector from "../flow-type-selector/FlowTypeSelector.vue";
import type { FlowCard, FlowKind } from "../../flow";

const props = defineProps<{
  show: boolean;
  flows: FlowCard[];
  kind: FlowKind;
  title?: string;
  datasetId?: string;
}>();

const emit = defineEmits<{
  "update:show": [value: boolean];
  complete: [result: unknown];
}>();

const step = ref<"select" | "execute">("select");
const selectedFlow = ref<FlowCard | null>(null);

watch(
  () => props.show,
  (visible) => {
    if (visible) {
      step.value = "select";
      selectedFlow.value = null;
    }
  },
);

const modalTitle = computed(() => {
  if (step.value === "execute" && selectedFlow.value) {
    return selectedFlow.value.label;
  }

  return props.title ?? (props.kind === "import" ? "Import" : props.kind === "export" ? "Export" : "Preview");
});

function handleSelect(plugin: FlowCard): void {
  selectedFlow.value = plugin;
  step.value = "execute";
}

function handleComplete(result?: unknown): void {
  emit("complete", result);
  emit("update:show", false);
}

function handleCancel(): void {
  if (step.value === "execute") {
    step.value = "select";
    selectedFlow.value = null;
    return;
  }

  emit("update:show", false);
}

function handleBack(): void {
  step.value = "select";
  selectedFlow.value = null;
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
      <FlowTypeSelector :flows="flows" @select="handleSelect" />
    </template>
    <template v-else-if="step === 'execute' && selectedFlow">
      <component
        :is="selectedFlow.component"
        v-if="kind === 'import'"
        :dataset-id="datasetId ?? ''"
        :on-complete="handleComplete"
        :on-cancel="handleCancel"
      />
      <component
        :is="selectedFlow.component"
        v-else-if="kind === 'export'"
        :dataset-id="datasetId ?? ''"
        :on-complete="handleComplete"
        :on-cancel="handleCancel"
      />
      <component
        :is="selectedFlow.component"
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
