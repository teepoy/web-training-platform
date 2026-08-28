<script setup lang="ts">
import ModelsView from "@/features/prediction/presentation/pages/PredictionJobsView.vue";

const props = defineProps<{ datasetId: string; compatibleViewTypes?: string[] }>();
</script>

<template>
  <ModelsView
    :dataset-id="props.datasetId"
    :compatible-view-types="props.compatibleViewTypes ?? []"
    embedded
  />
</template>
