<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { NSelect } from "naive-ui";
import {
  SC_SAMPLING_SIZE_FIELDS,
  type ScSamplingSizeField,
} from "@/features/sc/domain/samplingRules";

const { t } = useI18n();
const sizeOptions = computed(() =>
  SC_SAMPLING_SIZE_FIELDS.map((option) => ({
    ...option,
    label: t(
      `sc.${option.value === "size_x" ? "width" : option.value === "size_y" ? "height" : option.value === "size_d" ? "diameter" : "area"}`,
    ),
  })),
);

defineProps<{ value: ScSamplingSizeField }>();

const emit = defineEmits<{
  (e: "update:value", value: ScSamplingSizeField): void;
}>();
</script>

<template>
  <label class="field-label">{{ t("sc.sizeMetric") }}</label>
  <NSelect :value="value" :options="sizeOptions" @update:value="emit('update:value', $event)" />
</template>

<style scoped>
.field-label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 600;
}
</style>
