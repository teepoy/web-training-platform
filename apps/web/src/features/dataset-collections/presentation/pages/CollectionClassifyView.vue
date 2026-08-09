<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import ReclassifyPage from "@/features/sc/presentation/pages/ReclassifyPage.vue";

const route = useRoute();
const datasetKey = computed(
  () =>
    `${String(route.params.collectionId)}:${String(route.query.revisionId)}:${String(route.params.id)}`,
);
</script>

<template>
  <ReclassifyPage :key="datasetKey" />
</template>
