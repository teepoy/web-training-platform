<script setup lang="ts">
import { computed } from "vue";
import { NTag } from "naive-ui";
import { useI18n } from "vue-i18n";

const props = defineProps<{ status: string }>();
const { t, te } = useI18n();

type TagType = "default" | "info" | "success" | "error" | "warning";

const type = computed<TagType>(() => {
  const status = props.status.toLowerCase();
  if (status === "running") return "info";
  if (status === "completed" || status === "ready" || status === "active") return "success";
  if (status === "failed" || status === "error") return "error";
  if (status === "cancelled" || status === "paused") return "warning";
  return "default";
});

const label = computed(() => {
  const key = `status.${props.status.toLowerCase()}`;
  return te(key)
    ? t(key)
    : props.status.replace(/_/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
});
</script>

<template>
  <NTag :type="type" size="small" round>{{ label }}</NTag>
</template>
