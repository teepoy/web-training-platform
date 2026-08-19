<script setup lang="ts">
import { NSelect } from "naive-ui";
import {
  SC_SAMPLING_SIZE_FIELDS,
  type ScSamplingSizeField,
} from "@/features/sc/domain/samplingRules";

defineProps<{ value: ScSamplingSizeField }>();

const emit = defineEmits<{
  (e: "update:value", value: ScSamplingSizeField): void;
}>();
</script>

<template>
  <label class="field-label">Size metric</label>
  <NSelect
    :value="value"
    :options="SC_SAMPLING_SIZE_FIELDS"
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
