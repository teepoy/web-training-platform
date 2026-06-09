<script setup lang="ts">
import { computed } from "vue";
import { useGetDatasetApiV1DatasetsDatasetIdGet, useGetDatasetStatusApiV1DatasetsDatasetIdStatusGet } from "@/generated/orval/endpoints/api";
import type { Dataset, DatasetStatusResponse } from "@/generated/orval/models";
import JobsView from "@/features/training/presentation/pages/TrainingJobsView.vue";

const props = defineProps<{ datasetId: string }>();

const { data: datasetDetailRaw } = useGetDatasetApiV1DatasetsDatasetIdGet(computed(() => props.datasetId));
const { data: dsStatusRaw } = useGetDatasetStatusApiV1DatasetsDatasetIdStatusGet(
  computed(() => props.datasetId),
);

const datasetDetail = computed<Dataset | null>(() => {
  const raw = datasetDetailRaw.value;
  if (!raw) return null;
  const inner = (raw as { data: Dataset }).data;
  if (inner && typeof inner.id === "string") return inner;
  return null;
});

const dsStatus = computed<DatasetStatusResponse | null>(() => {
  const raw = dsStatusRaw.value;
  if (!raw) return null;
  const inner = (raw as { data: DatasetStatusResponse }).data;
  if (inner && typeof (inner as DatasetStatusResponse).allow_train === "boolean") return inner;
  return null;
});

const allowTrain = computed(() => dsStatus.value?.allow_train ?? false);

const compatibleViewTypes = computed(() => datasetDetail.value?.view_types ?? []);
</script>

<template>
  <JobsView
    v-if="datasetDetail"
    :datasetId="props.datasetId"
    :allow-train="allowTrain"
    :compatible-view-types="compatibleViewTypes"
  />
</template>
