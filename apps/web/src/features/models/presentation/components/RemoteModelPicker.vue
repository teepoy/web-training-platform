<script setup lang="ts">
import type { ModelResponse } from "@/generated/orval/models";
import ModelSearchSurface from "./ModelSearchSurface.vue";

const props = withDefaults(
  defineProps<{
    modelValue: string | null;
    active: boolean;
    compatibleViewIds?: string[];
  }>(),
  { compatibleViewIds: () => [] },
);

const emit = defineEmits<{
  (event: "update:modelValue", value: string | null): void;
  (event: "update:selectedModel", value: ModelResponse | null): void;
}>();
</script>

<template>
  <ModelSearchSurface
    mode="selection"
    :model-value="props.modelValue"
    :active="props.active"
    :compatible-view-ids="props.compatibleViewIds"
    :max-height="320"
    data-testid="remote-model-picker"
    @update:model-value="emit('update:modelValue', $event)"
    @update:selected-model="emit('update:selectedModel', $event)"
  />
</template>
