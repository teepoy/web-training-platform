<script setup lang="ts">
import { NSelect } from "naive-ui";

defineProps<{
  value: number[];
  options: Array<{ label: string; value: number }>;
  loading: boolean;
}>();

const emit = defineEmits<{
  (e: "update:value", value: number[]): void;
}>();
</script>

<template>
  <label class="field-label">Class Codes</label>
  <NSelect
    :value="value"
    multiple
    filterable
    :loading="loading"
    :options="options"
    placeholder="Select Class Codes"
    @update:value="emit('update:value', $event)"
  />
</template>

<style scoped>
.field-label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 600;
}
</style>
