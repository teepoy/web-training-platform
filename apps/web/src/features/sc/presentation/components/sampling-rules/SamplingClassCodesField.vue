<script setup lang="ts">
import { NSelect } from "naive-ui";
import { useI18n } from "vue-i18n";

const { t } = useI18n();

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
  <label class="field-label">{{ t("sc.classCodes") }}</label>
  <NSelect
    :value="value"
    multiple
    filterable
    :loading="loading"
    :options="options"
    :placeholder="t('sc.selectClassCodes')"
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
