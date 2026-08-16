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
      preset="card"
      title="Choose a model for prediction"
      class="model-picker-modal"
      :style="{ width: 'min(960px, calc(100vw - 32px))' }"
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
          <n-form-item label="Model" path="model_id" label-placement="top">
            <div class="model-picker">
              <n-text depth="3">
                Search and page through the complete model history. Newest models are shown first.
              </n-text>
              <div class="model-picker-filters">
                <n-input
                  v-model:value="modelSearch"
                  clearable
                  placeholder="Search model name, ID, source, trainer, or creator"
                />
                <n-select
                  v-model:value="modelSourceType"
                  clearable
                  :options="modelSourceOptions"
                  placeholder="All training sources"
                />
                <n-select
                  v-model:value="modelCreatorId"
                  clearable
                  filterable
                  :options="modelCreatorOptions"
                  placeholder="All creators"
                />
              </div>
              <n-data-table
                :columns="modelPickerColumns"
                :data="availableModels"
                :loading="modelsLoading"
                :pagination="modelPagination"
                :row-key="(row: ModelResponse) => row.id"
                :checked-row-keys="formModel.model_id ? [formModel.model_id] : []"
                :row-props="modelRowProps"
                :scroll-x="820"
                remote
                size="small"
                @update:checked-row-keys="selectModel"
              >
                <template #empty>
                  <n-empty description="No models match these filters" />
                </template>
              </n-data-table>
            </div>
          </n-form-item>
        </template>
        <template v-else>
          <div style="padding: 16px 0; text-align: center; color: var(--n-text-color-2)">
            Select an organization first.
          </div>
        </template>
      </n-form>
      <template #footer>
        <n-space justify="space-between" align="center">
          <n-text depth="3">
            {{
              selectedModel ? `Selected: ${modelDisplayName(selectedModel)}` : "Select one model"
            }}
          </n-text>
          <n-space>
            <n-button @click="onCancel">Cancel</n-button>
            <n-button
              type="primary"
              :disabled="!formModel.model_id || !formModel.dataset_id"
              :loading="runMutation.isPending.value"
              @click="onSubmit"
            >
              Start with selected model
            </n-button>
          </n-space>
        </n-space>
      </template>
    </n-modal>

    <TaskInsightModal v-model:show="insightVisible" :task="selectedTask" :handoff-enabled="false" />
  </n-space>
</template>

<script setup lang="ts">
import { ref, computed, h, provide, reactive, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useQuery, useQueryClient } from "@tanstack/vue-query";
import { refDebounced } from "@vueuse/core";
import type {
  DataTableColumns,
  DataTableRowKey,
  FormInst,
  FormRules,
  PaginationProps,
  SelectOption,
} from "naive-ui";
import { useMessage, NButton, NTag, NText } from "naive-ui";
import { useOrgStore } from "@/features/auth/application/org";
import {
  useListModelCreatorsApiV1ModelsCreatorsGet,
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
const showModal = ref(false);
const formRef = ref<FormInst | null>(null);
const formModel = ref({
  dataset_id: props.datasetId ?? null,
  model_id: null as string | null,
});
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
const modelSourceType = ref<"dataset" | "collection" | null>(null);
const modelCreatorId = ref<string | null>(null);
const modelPagination = reactive<PaginationProps>({
  page: 1,
  pageSize: 20,
  itemCount: 0,
  showSizePicker: true,
  pageSizes: [10, 20, 50, 100],
  onUpdatePage: (page: number) => {
    modelPagination.page = page;
  },
  onUpdatePageSize: (pageSize: number) => {
    modelPagination.pageSize = pageSize;
    modelPagination.page = 1;
  },
});
const modelListParams = computed(() => ({
  offset: ((modelPagination.page ?? 1) - 1) * (modelPagination.pageSize ?? 20),
  limit: modelPagination.pageSize ?? 20,
  q: debouncedModelSearch.value.trim() || undefined,
  source_type: modelSourceType.value ?? undefined,
  creator_id: modelCreatorId.value ?? undefined,
  sort_by: "created_at" as const,
  sort_order: "desc" as const,
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
          modelSourceType.value,
          modelCreatorId.value,
          modelPagination.page,
          modelPagination.pageSize,
        ]),
      ),
      enabled: computed(() => !!orgStore.currentOrgId && showModal.value),
    },
  },
);

const availableModels = computed<ModelResponse[]>(
  () => (modelsPage.value?.items ?? []) as ModelResponse[],
);
const selectedModelRecord = ref<ModelResponse | null>(null);
const selectedModel = computed(
  () =>
    availableModels.value.find((model) => model.id === formModel.value.model_id) ??
    (selectedModelRecord.value?.id === formModel.value.model_id ? selectedModelRecord.value : null),
);

watch(
  () => modelsPage.value?.total ?? 0,
  (total) => {
    modelPagination.itemCount = total;
  },
  { immediate: true },
);

watch([debouncedModelSearch, modelSourceType, modelCreatorId], () => {
  modelPagination.page = 1;
});

const modelSourceOptions: SelectOption[] = [
  { label: "Dataset", value: "dataset" },
  { label: "Collection", value: "collection" },
];
const { data: modelCreators } = useListModelCreatorsApiV1ModelsCreatorsGet({
  query: {
    queryKey: computed(() => orgScopedQueryKey(orgStore.currentOrgId, ["models", "creators"])),
    enabled: computed(() => !!orgStore.currentOrgId && showModal.value),
  },
});
const modelCreatorOptions = computed<SelectOption[]>(() =>
  (modelCreators.value ?? []).map((creator) => ({ label: creator.name, value: creator.id })),
);

function modelDisplayName(model: ModelResponse): string {
  return model.name?.trim() || model.id.slice(0, 8);
}

function modelSourceName(model: ModelResponse): string {
  if (model.dataset_id) return `Dataset · ${model.dataset_name?.trim() || model.dataset_id}`;
  if (model.collection_id) {
    return `Collection · ${model.collection_name?.trim() || model.collection_id}`;
  }
  return "Unknown source";
}

const modelPickerColumns = computed<DataTableColumns<ModelResponse>>(() => [
  { type: "selection", multiple: false, width: 42 },
  {
    title: "Model",
    key: "name",
    minWidth: 180,
    render: (model) =>
      h("div", {}, [
        h(NText, { strong: true }, { default: () => modelDisplayName(model) }),
        h("div", { class: "model-picker-id" }, model.id),
      ]),
  },
  {
    title: "Training source",
    key: "source",
    minWidth: 190,
    render: (model) => modelSourceName(model),
  },
  { title: "Trainer", key: "trainer_name", minWidth: 130 },
  {
    title: "Creator",
    key: "creator_name",
    minWidth: 130,
    render: (model) => model.creator_name?.trim() || model.created_by,
  },
  {
    title: "Created",
    key: "created_at",
    width: 170,
    render: (model) => (model.created_at ? new Date(model.created_at).toLocaleString() : "—"),
  },
]);

function selectModel(keys: DataTableRowKey[]): void {
  formModel.value.model_id = keys.length ? String(keys[keys.length - 1]) : null;
  selectedModelRecord.value =
    availableModels.value.find((model) => model.id === formModel.value.model_id) ?? null;
}

function modelRowProps(model: ModelResponse): Record<string, unknown> {
  return {
    style: { cursor: "pointer" },
    onClick: () => {
      formModel.value.model_id = model.id;
      selectedModelRecord.value = model;
    },
  };
}

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

const insightVisible = ref(false);
const selectedTask = ref<TaskTrackerSummary | null>(null);

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
  showModal.value = false;
  resetForm();
}

function resetForm() {
  formModel.value = { dataset_id: props.datasetId ?? null, model_id: null };
  selectedModelRecord.value = null;
  modelSearch.value = "";
  modelSourceType.value = null;
  modelCreatorId.value = null;
  modelPagination.page = 1;
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

.model-picker {
  display: grid;
  gap: 12px;
  width: 100%;
}

.model-picker-filters {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) 190px 190px;
  gap: 8px;
}

.model-picker-id {
  max-width: 190px;
  margin-top: 2px;
  overflow: hidden;
  color: var(--n-text-color-3);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 640px) {
  .embedded-section-header {
    align-items: stretch;
    flex-direction: column;
  }

  .embedded-section-header :deep(.n-button) {
    width: 100%;
  }

  .model-picker-filters {
    grid-template-columns: 1fr;
  }
}
</style>
