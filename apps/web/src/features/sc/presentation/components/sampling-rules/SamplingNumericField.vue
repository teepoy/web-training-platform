<script setup lang="ts">
import { NInputNumber } from "naive-ui";

const props = withDefaults(
  defineProps<{
    label: string;
    value: number;
    minimum: number;
    maximum?: number;
    precision?: number;
    suffix?: string;
    compact?: boolean;
    testId?: string;
  }>(),
  {
    maximum: undefined,
    precision: 0,
    suffix: undefined,
    compact: false,
    testId: undefined,
  },
);

const emit = defineEmits<{
  (e: "update:value", value: number): void;
}>();

function updateValue(value: number | null): void {
  if (value !== null) emit("update:value", value);
}
</script>

<template>
  <label v-if="!compact" class="field-label">{{ label }}</label>
  <NInputNumber
    :value="value"
    :min="minimum"
    :max="maximum"
    :precision="precision"
    :aria-label="label"
    :data-testid="testId"
    :class="{ 'compact-input': compact }"
    @update:value="updateValue"
  >
    <template v-if="suffix" #suffix>{{ suffix }}</template>
  </NInputNumber>
</template>

<style scoped>
.field-label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 600;
}

.compact-input {
  width: 116px;
}
</style>
