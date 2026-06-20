<template>
  <n-space vertical size="large">
    <n-page-header title="Prediction Jobs">
      <template #extra>
        <n-button type="primary" @click="showModal = true">Start Prediction</n-button>
      </template>
    </n-page-header>
    <n-spin :show="isLoading">
      <n-data-table
        :columns="columns"
        :data="visibleJobs"
        :bordered="true"
        :striped="true"
        :loading="isLoading"
      />
    </n-spin>

    <n-modal
      v-model:show="showModal"
      preset="dialog"
      title="Start Prediction"
      positive-text="Start"
      negative-text="Cancel"
      :loading="runMutation.isPending.value"
      @positive-click="onSubmit"
      @negative-click="onCancel"
      >
        <n-form
          ref="formRef"
          :model="formModel"
          :rules="formRules"
          label-placement="left"
          label-width="auto"
        >
          <template v-if="orgStore.currentOrgId">
            <n-form-item label="Training Job" path="model_id">
              <n-select
                v-model:value="formModel.model_id"
                :options="completedJobOptions"
                :loading="jobsLoading"
                placeholder="Select a completed training job"
                filterable
              />
            </n-form-item>
          </template>
          <template v-else>
            <div style="padding: 16px 0; text-align: center; color: var(--n-text-color-2)">
              Select an organization first.
            </div>
          </template>
        </n-form>
      </n-modal>
  </n-space>
</template>

<script setup lang="ts">
import { ref, computed, h } from "vue";
import { useQuery, useQueryClient } from "@tanstack/vue-query";
import type { DataTableColumns, FormInst, FormRules, SelectOption } from "naive-ui";
import { useMessage, NTag } from "naive-ui";
import { useOrgStore } from "@/features/auth/application/org";
import {
  useListJobsApiV1TrainingJobsGet,
  useRunPredictionsApiV1PredictionsRunPost,
} from "@/generated/orval/endpoints/api";
import { listPredictionJobs } from "@/shared/api/predictions";
import type { PredictionJobResponse as PredictionJob, TrainingJob } from "@/generated/orval/models";
import type { RunPredictionRequest } from "@/generated/orval/models";

const props = defineProps<{ datasetId?: string | null }>();

const message = useMessage();
const qc = useQueryClient();
const orgStore = useOrgStore();

const { data: jobs, isLoading } = useQuery({
  queryKey: computed(() => ["prediction-jobs", orgStore.currentOrgId, props.datasetId ?? null]),
  queryFn: () => listPredictionJobs(props.datasetId),
  refetchInterval: 5000,
});

const visibleJobs = computed<PredictionJob[]>(() => jobs.value ?? []);

const { data: allJobs, isLoading: jobsLoading } = useListJobsApiV1TrainingJobsGet(undefined, {
  query: {
    select: (response: any) => response.data,
    queryKey: computed(() => ["jobs", "prediction-launcher", orgStore.currentOrgId]),
    enabled: computed(() => !!orgStore.currentOrgId),
    refetchInterval: 5000,
  },
});

const completedJobs = computed<TrainingJob[]>(() =>
  (allJobs.value ?? []).filter(
    (j: any) =>
      j.status === "completed" &&
      (props.datasetId ? j.dataset_id === props.datasetId : true),
  ),
);

const completedJobOptions = computed<SelectOption[]>(() =>
  completedJobs.value
    .map((j) => {
      const modelArtifact = (j.artifact_refs ?? []).find(
        (a) => a.kind === "model",
      );
      return { job: j, artifactId: modelArtifact?.id ?? null };
    })
    .filter(({ artifactId }) => artifactId != null)
    .map(({ job: j, artifactId }) => ({
      label: `${j.trainer_id} — ${(j.id ?? "").slice(0, 8)}…`,
      value: artifactId as string,
    })),
);

type TagType = "default" | "info" | "success" | "error" | "warning";

function statusType(status: string): TagType {
  const normalized = status.toLowerCase();
  if (normalized === "running") return "info";
  if (normalized === "completed") return "success";
  if (normalized === "failed") return "error";
  if (normalized === "cancelled") return "warning";
  return "default";
}

const columns = computed<DataTableColumns<PredictionJob>>(() => [
  {
    title: "ID",
    key: "id",
    width: 120,
    render: (row) => row.id.slice(0, 8) + "…",
  },
  {
    title: "Status",
    key: "status",
    width: 130,
    render: (row) =>
      h(
        NTag,
        { type: statusType(row.status), size: "small", round: true },
        { default: () => row.status },
      ),
  },
  {
    title: "Dataset ID",
    key: "dataset_id",
    ellipsis: { tooltip: true },
    render: (row) => row.dataset_id.slice(0, 8) + "…",
  },
  {
    title: "Model ID",
    key: "model_id",
    ellipsis: { tooltip: true },
    render: (row) => row.model_id.slice(0, 8) + "…",
  },
  {
    title: "Target",
    key: "target",
    width: 160,
  },
  {
    title: "Created At",
    key: "created_at",
    width: 180,
    render: (row) => new Date(row.created_at).toLocaleString(),
  },
]);

const showModal = ref(false);
const formRef = ref<FormInst | null>(null);
const formModel = ref({ model_id: null as string | null });

const formRules: FormRules = {
  model_id: [{ required: true, message: "Please select a completed training job", trigger: ["blur", "change"] }],
};

const runMutation = useRunPredictionsApiV1PredictionsRunPost({
  mutation: {
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prediction-jobs"] });
      message.success("Prediction started");
      showModal.value = false;
      resetForm();
    },
    onError: (err: Error) => {
      message.error(err.message ?? "Failed to start prediction");
    },
  },
});

function onSubmit() {
  formRef.value?.validate((errors) => {
    if (errors) return;
    if (!formModel.value.model_id || !props.datasetId) return;

    const request: RunPredictionRequest = {
      model_id: formModel.value.model_id,
      dataset_id: props.datasetId,
    };

    runMutation.mutate({ data: request });
  });
  return false;
}

function onCancel() {
  resetForm();
}

function resetForm() {
  formModel.value = { model_id: null };
  formRef.value?.restoreValidation();
}
</script>
