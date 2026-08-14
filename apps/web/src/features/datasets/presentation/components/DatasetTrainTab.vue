<script setup lang="ts">
import type { Dataset } from "@/generated/orval/models";
import JobsView from "@/features/training/presentation/pages/TrainingJobsView.vue";

const props = defineProps<{ datasetId: string; dataset: Dataset }>();
</script>

<template>
  <JobsView
    :dataset-id="props.datasetId"
    :compatible-view-types="props.dataset.view_types"
    embedded
  />
</template>
