<script setup lang="ts">
import { computed } from "vue";
import {
  useGetDatasetApiV1DatasetsDatasetIdGet,
  useGetDatasetStatusApiV1DatasetsDatasetIdStatusGet,
} from "@/generated/orval/endpoints/api";
import type { Dataset, DatasetStatusResponse } from "@/generated/orval/models";
import JobsView from "@/features/training/presentation/pages/TrainingJobsView.vue";

const props = defineProps<{ datasetId: string }>();

const { data: datasetDetailRaw } = useGetDatasetApiV1DatasetsDatasetIdGet(
  computed(() => props.datasetId),
);
const {
  data: dsStatusRaw,
  isLoading: statusLoading,
  isError: statusError,
} = useGetDatasetStatusApiV1DatasetsDatasetIdStatusGet(computed(() => props.datasetId));

const datasetDetail = computed<Dataset | null>(() => {
  const raw = datasetDetailRaw.value;
  if (!raw) return null;
  if (typeof raw.id === "string") return raw;
  return null;
});

const dsStatus = computed<DatasetStatusResponse | null>(() => {
  const raw = dsStatusRaw.value;
  if (!raw) return null;
  if (typeof raw.allow_train === "boolean") return raw;
  return null;
});

const allowTrain = computed(() => dsStatus.value?.allow_train ?? false);

const trainDisabledReason = computed<string | null>(() => {
  if (statusLoading.value) return "Checking training readiness…";
  if (statusError.value) return "Training readiness could not be loaded.";
  const status = dsStatus.value;
  if (!status) return "Training readiness is unavailable.";
  if (status.allow_train) return null;
  if (status.train_disabled_reason === "insufficient_active_classes") {
    return `Training requires at least ${status.minimum_active_class_count} active classes; currently ${status.active_class_count}.`;
  }
  return "Training is unavailable for this dataset.";
});

const compatibleViewTypes = computed(() => datasetDetail.value?.view_types ?? []);
</script>

<template>
  <JobsView
    v-if="datasetDetail"
    :datasetId="props.datasetId"
    :allow-train="allowTrain"
    :train-disabled-reason="trainDisabledReason"
    :compatible-view-types="compatibleViewTypes"
  />
</template>
