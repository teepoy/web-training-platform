<script setup lang="ts">
import JobsView from "@/features/training/presentation/pages/TrainingJobsView.vue";

const props = defineProps<{ datasetId: string }>();
</script>

<template>
  <n-space vertical>
    <n-text depth="3" style="font-size: 13px">Training jobs for this dataset</n-text>
    <JobsView :datasetId="props.datasetId" />
  </n-space>
</template>
