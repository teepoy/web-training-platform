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
        <n-form-item label="Target">
          <n-input :value="predictionTarget" disabled />
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
      <n-result status="success" :title="resultTitle" :description="resultDescription">
        <template #footer>
          <n-space vertical>
            <n-descriptions bordered :column="2">
              <n-descriptions-item label="Prediction Job">
                {{ result.id }}
              </n-descriptions-item>
              <n-descriptions-item label="Status">
                {{ result.status }}
              </n-descriptions-item>
              <n-descriptions-item label="Model Version">
                {{ result.model_version || '-' }}
              </n-descriptions-item>
              <n-descriptions-item label="Target">
                {{ result.target }}
              </n-descriptions-item>
            </n-descriptions>
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
import type { Model, PredictionJob } from "../types";
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

const predictionTarget = computed(() => {
  const targets = props.model?.metadata?.prediction_targets;
  if (Array.isArray(targets) && typeof targets[0] === "string") {
    return targets[0];
  }
  return "image_classification";
});

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

const result = ref<PredictionJob | null>(null);

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
      target: predictionTarget.value,
    });
  },
  onSuccess: (data) => {
    result.value = data;
    qc.invalidateQueries({ queryKey: ["prediction-jobs"] });
    message.success("Prediction job submitted");
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

const resultTitle = computed(() => {
  if (!result.value) return "";
  return "Prediction Job Submitted";
});

const resultDescription = computed(() => {
  if (!result.value) return "";
  return "The batch prediction run is executing asynchronously. Check job status via the prediction job APIs and Label Studio.";
});

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
