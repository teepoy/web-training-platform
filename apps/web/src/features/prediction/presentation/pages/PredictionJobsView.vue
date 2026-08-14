<template>
  <n-space vertical size="large">
    <template v-if="!orgStore.currentOrgId">
      <div class="no-org-state">
        <n-empty description="You are not a member of any organization. Contact an admin." />
      </div>
    </template>
    <template v-else>
      <n-page-header v-if="!props.embedded" title="Prediction Jobs">
        <template #extra>
          <n-button type="primary" @click="showModal = true"> Start Prediction </n-button>
        </template>
      </n-page-header>
      <div v-else class="embedded-section-header">
        <div>
          <n-h3 class="embedded-section-title">Prediction runs</n-h3>
          <n-text depth="3">Run a model on this dataset and review its recent outputs.</n-text>
        </div>
        <n-button type="primary" @click="showModal = true">Start Prediction</n-button>
      </div>
      <n-spin :show="isLoading">
        <n-data-table
          :columns="columns"
          :data="visibleJobs"
          :bordered="true"
          :striped="true"
          :loading="isLoading"
          :row-key="predictionJobRowKey"
          :scroll-x="props.embedded ? 640 : 760"
        >
          <template #empty>
            <n-empty
              :description="
                props.datasetId
                  ? 'No prediction runs for this dataset yet'
                  : 'No prediction runs yet'
              "
            />
          </template>
        </n-data-table>
      </n-spin>
    </template>

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
          <n-form-item v-if="!props.datasetId" label="Dataset" path="dataset_id">
            <n-select
              v-model:value="formModel.dataset_id"
              :options="datasetOptions"
              :loading="datasetsLoading"
              placeholder="Select a dataset"
              filterable
            />
          </n-form-item>
          <n-form-item label="Model" path="model_id">
            <n-empty
              v-if="!modelsLoading && modelOptions.length === 0"
              description="No models are available for prediction"
            />
            <n-select
              v-else
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
import { ref, computed, h, provide, watch } from "vue";
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
import { listDatasets } from "@/shared/api/datasets";
import { orgScopedQueryKey, toUserMessage } from "@/shared/api";
import TaskInsightModal, { TASK_INSIGHT_ORG_ID_KEY } from "@/shared/components/task-insight-modal";
import type {
  ModelResponse,
  PredictionJobResponse as PredictionJob,
  TaskTrackerSummaryResponse as TaskTrackerSummary,
} from "@/generated/orval/models";
import type { RunPredictionRequest } from "@/generated/orval/models";

const props = withDefaults(defineProps<{ datasetId?: string | null; embedded?: boolean }>(), {
  embedded: false,
});

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
  enabled: computed(() => !!orgStore.currentOrgId),
});

const visibleJobs = computed<PredictionJob[]>(() => jobs.value ?? []);

const { data: datasets, isLoading: datasetsLoading } = useQuery({
  queryKey: computed(() =>
    orgScopedQueryKey(orgStore.currentOrgId, ["datasets", "prediction-launcher"]),
  ),
  queryFn: listDatasets,
  enabled: computed(() => !!orgStore.currentOrgId && !props.datasetId),
});
const datasetOptions = computed<SelectOption[]>(() =>
  (datasets.value ?? []).map((dataset) => ({
    label: dataset.name,
    value: dataset.id,
  })),
);

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

const columns = computed<DataTableColumns<PredictionJob>>(() => {
  const baseColumns: DataTableColumns<PredictionJob> = [
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
  ];
  return props.embedded
    ? baseColumns.filter((column) => !("key" in column) || column.key !== "dataset_id")
    : baseColumns;
});

const showModal = ref(false);
const insightVisible = ref(false);
const selectedTask = ref<TaskTrackerSummary | null>(null);
const formRef = ref<FormInst | null>(null);
const formModel = ref({
  dataset_id: props.datasetId ?? null,
  model_id: null as string | null,
});

watch(
  () => props.datasetId,
  (datasetId) => {
    formModel.value.dataset_id = datasetId ?? null;
  },
);

const formRules: FormRules = {
  dataset_id: [{ required: true, message: "Please select a dataset", trigger: ["change"] }],
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
    if (!formModel.value.model_id || !formModel.value.dataset_id) return;

    const request: RunPredictionRequest = {
      model_id: formModel.value.model_id,
      dataset_id: formModel.value.dataset_id,
    };

    runMutation.mutate({ data: request });
  });
  return false;
}

function onCancel() {
  resetForm();
}

function resetForm() {
  formModel.value = { dataset_id: props.datasetId ?? null, model_id: null };
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

<style scoped>
.no-org-state {
  padding: 48px;
  text-align: center;
}

.embedded-section-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding-top: 4px;
}

.embedded-section-title {
  margin: 0 0 2px;
}

@media (max-width: 640px) {
  .embedded-section-header {
    align-items: stretch;
    flex-direction: column;
  }

  .embedded-section-header :deep(.n-button) {
    width: 100%;
  }
}
</style>
