<script setup lang="ts">
import ModelsView from "@/features/prediction/presentation/pages/PredictionJobsView.vue";

const props = defineProps<{ datasetId: string }>();
</script>

<template>
  <ModelsView :dataset-id="props.datasetId" embedded />
</template>
