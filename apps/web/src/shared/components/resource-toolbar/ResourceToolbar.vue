<script setup lang="ts">
import { NH2, NSpace } from "naive-ui";
import { useI18n } from "vue-i18n";

const { t } = useI18n();

const props = withDefaults(
  defineProps<{
    title?: string;
  }>(),
  {
    title: undefined,
  },
);
</script>

<template>
  <div>
    <n-space justify="space-between" align="center" style="margin-bottom: 16px">
      <n-h2 style="margin: 0">{{ props.title ?? t("resources.datasets") }}</n-h2>
    </n-space>
  </div>
</template>
