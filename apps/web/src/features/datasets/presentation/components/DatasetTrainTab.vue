<script setup lang="ts">
import { computed } from "vue";
import { useGetDatasetApiV1DatasetsDatasetIdGet } from "@/generated/orval/endpoints/api";
import type { Dataset } from "@/generated/orval/models";
import JobsView from "@/features/training/presentation/pages/TrainingJobsView.vue";

const props = defineProps<{ datasetId: string }>();

const { data: datasetDetailRaw } = useGetDatasetApiV1DatasetsDatasetIdGet(
  computed(() => props.datasetId),
);
const datasetDetail = computed<Dataset | null>(() => {
  const raw = datasetDetailRaw.value;
  if (!raw) return null;
  if (typeof raw.id === "string") return raw;
  return null;
});

const compatibleViewTypes = computed(() => datasetDetail.value?.view_types ?? []);
</script>

<template>
  <JobsView
    v-if="datasetDetail"
    :datasetId="props.datasetId"
    :compatible-view-types="compatibleViewTypes"
  />
</template>
