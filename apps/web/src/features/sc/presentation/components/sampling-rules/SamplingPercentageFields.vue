<script setup lang="ts">
import SamplingNumericField from "./SamplingNumericField.vue";

withDefaults(
  defineProps<{
    percentage: number;
    compact?: boolean;
  }>(),
  { compact: false },
);

const emit = defineEmits<{
  (e: "update:percentage", value: number): void;
}>();
</script>

<template>
  <SamplingNumericField
    label="Percentage"
    :value="percentage"
    :minimum="0.01"
    :maximum="100"
    :precision="2"
    suffix="%"
    :compact="compact"
    test-id="sampling-percentage"
    @update:value="emit('update:percentage', $event)"
  />
</template>
