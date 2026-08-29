<script setup lang="ts">
import { useI18n } from "vue-i18n";
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
const { t } = useI18n();
</script>

<template>
  <SamplingNumericField
    :label="t('sc.percentage')"
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
