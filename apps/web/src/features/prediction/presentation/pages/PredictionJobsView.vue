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
        :row-key="predictionJobRowKey"
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
          <n-form-item label="Model" path="model_id">
            <n-select
              v-model:value="formModel.model_id"
              :options="modelOptions"
              :loading="modelsLoading"
              placeholder="Select a model"
              filterable
              remote
              @search="modelSearch = $event"
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

    <TaskInsightModal v-model:show="insightVisible" :task="selectedTask" :handoff-enabled="false" />
  </n-space>
</template>

<script setup lang="ts">
import { ref, computed, h, provide } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useQuery, useQueryClient } from "@tanstack/vue-query";
import { refDebounced } from "@vueuse/core";
import type { DataTableColumns, FormInst, FormRules, SelectOption } from "naive-ui";
import { useMessage, NButton, NTag } from "naive-ui";
import { useOrgStore } from "@/features/auth/application/org";
import {
  useListModelsApiV1ModelsGet,
  useRunPredictionsApiV1PredictionsRunPost,
} from "@/generated/orval/endpoints/api";
import { listPredictionJobs } from "@/shared/api/predictions";
import { orgScopedQueryKey, toUserMessage } from "@/shared/api";
import TaskInsightModal, { TASK_INSIGHT_ORG_ID_KEY } from "@/shared/components/task-insight-modal";
import type {
  ModelResponse,
  PredictionJobResponse as PredictionJob,
  TaskTrackerSummaryResponse as TaskTrackerSummary,
} from "@/generated/orval/models";
import type { RunPredictionRequest } from "@/generated/orval/models";

const props = defineProps<{ datasetId?: string | null }>();

const route = useRoute();
const router = useRouter();
const message = useMessage();
const qc = useQueryClient();
const orgStore = useOrgStore();
provide(
  TASK_INSIGHT_ORG_ID_KEY,
  computed(() => orgStore.currentOrgId),
);

const { data: jobs, isLoading } = useQuery({
  queryKey: computed(() =>
    orgScopedQueryKey(orgStore.currentOrgId, [
      "prediction-jobs",
      "all-pages",
      props.datasetId ?? null,
    ]),
  ),
  queryFn: () => listPredictionJobs(props.datasetId),
  refetchInterval: 5000,
});

const visibleJobs = computed<PredictionJob[]>(() => jobs.value ?? []);

function predictionJobRowKey(row: PredictionJob): string {
  return row.id;
}

const modelSearch = ref("");
const debouncedModelSearch = refDebounced(modelSearch, 250);
const modelListParams = computed(() => ({
  limit: 50,
  q: debouncedModelSearch.value.trim() || undefined,
}));
const { data: modelsPage, isLoading: modelsLoading } = useListModelsApiV1ModelsGet(
  modelListParams,
  {
    query: {
      queryKey: computed(() =>
        orgScopedQueryKey(orgStore.currentOrgId, [
          "models",
          "prediction-launcher",
          debouncedModelSearch.value.trim(),
        ]),
      ),
      enabled: computed(() => !!orgStore.currentOrgId),
      refetchInterval: 5000,
    },
  },
);

const modelOptions = computed<SelectOption[]>(() =>
  ((modelsPage.value?.items ?? []) as ModelResponse[]).map((model) => ({
    label: [model.name?.trim() || model.id.slice(0, 8), model.dataset_name, model.creator_name]
      .filter(Boolean)
      .join(" · "),
    value: model.id,
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
    render: (row) => (row.dataset_id ? row.dataset_id.slice(0, 8) + "…" : "Deleted dataset"),
  },
  {
    title: "Model ID",
    key: "model_id",
    ellipsis: { tooltip: true },
    render: (row) => row.model_id.slice(0, 8) + "…",
  },
  {
    title: "Created At",
    key: "created_at",
    width: 180,
    render: (row) => new Date(row.created_at).toLocaleString(),
  },
  {
    title: "Actions",
    key: "actions",
    width: 150,
    render: (row) =>
      h("span", { style: "display: inline-flex; gap: 8px" }, [
        h(
          NButton,
          {
            size: "small",
            tertiary: true,
            onClick: (event: Event) => {
              event.stopPropagation();
              openInsight(row);
            },
          },
          { default: () => "Task Progress" },
        ),
      ]),
  },
]);

const showModal = ref(false);
const insightVisible = ref(false);
const selectedTask = ref<TaskTrackerSummary | null>(null);
const formRef = ref<FormInst | null>(null);
const formModel = ref({ model_id: null as string | null });

const formRules: FormRules = {
  model_id: [{ required: true, message: "Please select a model", trigger: ["blur", "change"] }],
};

const runMutation = useRunPredictionsApiV1PredictionsRunPost({
  mutation: {
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: orgScopedQueryKey(orgStore.currentOrgId, ["prediction-jobs"]),
      });
      message.success("Prediction started");
      showModal.value = false;
      resetForm();
    },
    onError: (error) => {
      message.error(toUserMessage(error, "Failed to start prediction"));
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
  modelSearch.value = "";
  formRef.value?.restoreValidation();
}

function openTaskView(row: PredictionJob) {
  router.push({
    path: "/tasks",
    query: { kind: "prediction", task: row.id, from: route.fullPath },
  });
}

function openInsight(row: PredictionJob) {
  selectedTask.value = predictionTaskSummary(row);
  insightVisible.value = true;
}

function predictionTaskSummary(row: PredictionJob): TaskTrackerSummary {
  return {
    id: row.id,
    task_kind: "prediction",
    execution_kind: "predict-batch",
    display_name: "Prediction",
    display_status: row.status,
    stage:
      row.status === "completed" || row.status === "failed"
        ? "validation_output"
        : "queue_allocation",
    dataset_id: row.dataset_id,
    model_id: row.model_id,
    trainer_id: null,
    created_by: row.created_by,
    created_at: row.created_at,
    updated_at: row.updated_at,
    prefect_state: null,
    work_pool_name: null,
    work_queue_name: null,
    queue_priority: null,
    queue_priority_label: "none",
    queue_depth_ahead: null,
    capacity_status: "unknown",
    pool_concurrency_limit: null,
    pool_slots_used: null,
  };
}
</script>
