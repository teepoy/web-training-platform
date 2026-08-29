<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";

const props = defineProps<{
  datasetId?: string | null;
  collectionId?: string | null;
  collectionRevisionId?: string | null;
}>();
const { t } = useI18n();

const route = computed(() =>
  props.collectionId
    ? `/dataset-collections/${props.collectionId}`
    : props.datasetId
      ? `/datasets/${props.datasetId}`
      : null,
);
const label = computed(() => {
  if (props.collectionId) {
    const revision = props.collectionRevisionId?.slice(0, 8) ?? "unknown";
    return `${t("resources.collection")} ${props.collectionId.slice(0, 8)}… · ${t("resources.revision", { revision })}`;
  }
  if (props.datasetId) return `${t("resources.dataset")} ${props.datasetId.slice(0, 8)}…`;
  return t("resources.deletedTarget");
});
</script>

<template>
  <RouterLink v-if="route" :to="route" class="resource-target-link">{{ label }}</RouterLink>
  <span v-else>{{ label }}</span>
</template>

<style scoped>
.resource-target-link {
  color: var(--n-primary-color, #5267c9);
  text-decoration: none;
}

.resource-target-link:hover {
  text-decoration: underline;
}
</style>
