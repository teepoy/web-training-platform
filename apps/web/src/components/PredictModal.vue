<template>
  <n-modal
    :show="show"
    preset="card"
    title="Run Predictions"
    style="width: 600px"
    :bordered="false"
    @update:show="$emit('update:show', $event)"
  >
    <template v-if="!result">
      <n-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-placement="left"
        label-width="auto"
      >
        <n-form-item label="Model" path="modelId">
          <n-input :value="model?.name || model?.id.slice(0, 12) + '...'" disabled />
        </n-form-item>
        <n-form-item label="Dataset" path="datasetId">
          <n-select
            v-model:value="form.datasetId"
            :options="datasetOptions"
            placeholder="Select dataset to predict on"
            filterable
          />
        </n-form-item>
        <n-form-item label="Model Version Tag">
          <n-input
            v-model:value="form.modelVersion"
            placeholder="Optional tag for filtering in Label Studio"
          />
        </n-form-item>
        <n-form-item label="Samples">
          <n-radio-group v-model:value="form.predictionMode">
            <n-space>
              <n-radio value="all">All samples in dataset</n-radio>
              <n-radio value="specific">Specific samples</n-radio>
            </n-space>
          </n-radio-group>
        </n-form-item>
        <n-form-item v-if="form.predictionMode === 'specific'" label="Sample IDs">
          <n-dynamic-tags v-model:value="form.sampleIds" />
          <n-text depth="3" style="margin-left: 8px; font-size: 12px">
            Enter sample IDs and press Enter
          </n-text>
        </n-form-item>
      </n-form>
      <n-space justify="end" style="margin-top: 16px">
        <n-button @click="$emit('update:show', false)">Cancel</n-button>
        <n-button
          type="primary"
          :loading="mutation.isPending.value"
          @click="onSubmit"
        >
          Run Predictions
        </n-button>
      </n-space>
    </template>
    <template v-else>
      <n-result
        :status="result.failed === 0 ? 'success' : result.failed === result.total_samples ? 'error' : 'warning'"
        :title="resultTitle"
        :description="resultDescription"
      >
        <template #footer>
          <n-space vertical>
            <n-descriptions bordered :column="2">
              <n-descriptions-item label="Total Samples">
                {{ result.total_samples }}
              </n-descriptions-item>
              <n-descriptions-item label="Successful">
                <n-text type="success">{{ result.successful }}</n-text>
              </n-descriptions-item>
              <n-descriptions-item label="Failed">
                <n-text type="error">{{ result.failed }}</n-text>
              </n-descriptions-item>
              <n-descriptions-item label="Model Version">
                {{ result.model_version || '-' }}
              </n-descriptions-item>
              <n-descriptions-item label="Duration">
                {{ formatDuration(result.started_at, result.completed_at) }}
              </n-descriptions-item>
            </n-descriptions>
            <n-collapse v-if="failedPredictions.length > 0">
              <n-collapse-item title="Failed Predictions" name="errors">
                <n-list>
                  <n-list-item v-for="pred in failedPredictions" :key="pred.sample_id">
                    <n-thing :title="pred.sample_id.slice(0, 12) + '...'" :description="pred.error || ''" />
                  </n-list-item>
                </n-list>
              </n-collapse-item>
            </n-collapse>
            <n-space justify="center">
              <n-button @click="reset">Run Another</n-button>
              <n-button type="primary" @click="$emit('update:show', false)">Close</n-button>
            </n-space>
          </n-space>
        </template>
      </n-result>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import type { FormInst, FormRules, SelectOption } from "naive-ui";
import { useMessage } from "naive-ui";
import { api } from "../api";
import type { Model, BatchPredictionResult } from "../types";
import { useOrgStore } from "../stores/org";

const props = defineProps<{
  show: boolean;
  model: Model | null;
}>();

const emit = defineEmits<{
  (e: "update:show", value: boolean): void;
}>();

const message = useMessage();
const qc = useQueryClient();
const orgStore = useOrgStore();

// ---------------------------------------------------------------------------
// Form
// ---------------------------------------------------------------------------

const formRef = ref<FormInst | null>(null);
const form = ref({
  datasetId: null as string | null,
  modelVersion: "",
  predictionMode: "all" as "all" | "specific",
  sampleIds: [] as string[],
});

const rules: FormRules = {
  datasetId: [{ required: true, message: "Please select a dataset", trigger: "change" }],
};

// ---------------------------------------------------------------------------
// Dataset options
// ---------------------------------------------------------------------------

const { data: datasets } = useQuery({
  queryKey: computed(() => ["datasets", orgStore.currentOrgId]),
  queryFn: api.listDatasets,
  enabled: computed(() => !!orgStore.currentOrgId && props.show),
});

const datasetOptions = computed<SelectOption[]>(() =>
  (datasets.value ?? []).map((d) => ({ label: d.name, value: d.id }))
);

// ---------------------------------------------------------------------------
// Prefill dataset from model
// ---------------------------------------------------------------------------

watch(
  () => props.model,
  (model) => {
    if (model?.dataset_id) {
      form.value.datasetId = model.dataset_id;
    }
  },
  { immediate: true }
);

// ---------------------------------------------------------------------------
// Mutation
// ---------------------------------------------------------------------------

const result = ref<BatchPredictionResult | null>(null);

const mutation = useMutation({
  mutationFn: () => {
    if (!props.model || !form.value.datasetId) {
      throw new Error("Model and dataset are required");
    }
    return api.runPredictions({
      model_id: props.model.id,
      dataset_id: form.value.datasetId,
      sample_ids: form.value.predictionMode === "specific" && form.value.sampleIds.length > 0
        ? form.value.sampleIds
        : null,
      model_version: form.value.modelVersion || null,
    });
  },
  onSuccess: (data) => {
    result.value = data;
    qc.invalidateQueries({ queryKey: ["predictions"] });
    if (data.failed === 0) {
      message.success(`Successfully predicted ${data.successful} samples`);
    } else if (data.successful > 0) {
      message.warning(`Predicted ${data.successful} samples, ${data.failed} failed`);
    } else {
      message.error(`All ${data.failed} predictions failed`);
    }
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to run predictions");
  },
});

function onSubmit() {
  formRef.value?.validate((errors) => {
    if (errors) return;
    mutation.mutate();
  });
}

function reset() {
  result.value = null;
  form.value = {
    datasetId: props.model?.dataset_id ?? null,
    modelVersion: "",
    predictionMode: "all",
    sampleIds: [],
  };
}

// ---------------------------------------------------------------------------
// Result display
// ---------------------------------------------------------------------------

const failedPredictions = computed(() =>
  result.value?.predictions.filter((p) => p.error) ?? []
);

const resultTitle = computed(() => {
  if (!result.value) return "";
  if (result.value.failed === 0) return "Predictions Complete";
  if (result.value.successful === 0) return "Predictions Failed";
  return "Predictions Partially Complete";
});

const resultDescription = computed(() => {
  if (!result.value) return "";
  return `Predictions have been stored in Label Studio and can be viewed in the project.`;
});

function formatDuration(start: string, end: string): string {
  const startDate = new Date(start);
  const endDate = new Date(end);
  const ms = endDate.getTime() - startDate.getTime();
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

// ---------------------------------------------------------------------------
// Reset when modal opens
// ---------------------------------------------------------------------------

watch(
  () => props.show,
  (show) => {
    if (show) {
      reset();
    }
  }
);
</script>
