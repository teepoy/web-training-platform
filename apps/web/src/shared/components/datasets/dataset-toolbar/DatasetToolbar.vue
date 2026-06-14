<script setup lang="ts">
import { NH2, NSpace } from "naive-ui";

const props = withDefaults(
  defineProps<{
    title?: string;
  }>(),
  {
    title: "Datasets",
  },
);
</script>

<template>
  <div>
    <n-space justify="space-between" align="center" style="margin-bottom: 16px">
      <n-h2 style="margin: 0">{{ props.title }}</n-h2>
    </n-space>
  </div>
</template>
