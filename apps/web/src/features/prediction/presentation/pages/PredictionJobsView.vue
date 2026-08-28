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
      <div class="history-filters">
        <n-input v-model:value="jobSearch" clearable size="small" placeholder="Search jobs" />
        <n-select
          v-model:value="statusFilter"
          clearable
          size="small"
          :options="statusOptions"
          placeholder="All statuses"
        />
        <CreatorScopeSelect
          v-model="creatorScope"
          :creators="[]"
          resource-label="prediction jobs"
          class="history-creator-filter"
        />
        <n-button v-if="activeFilterCount > 0" size="small" quaternary @click="clearFilters">
          Clear filters ({{ activeFilterCount }})
        </n-button>
      </div>
      <n-spin :show="isLoading">
        <n-data-table
          :columns="columns"
          :data="visibleJobs"
          :bordered="true"
          :striped="true"
          :loading="isLoading"
          :pagination="jobsPagination"
          :row-key="predictionJobRowKey"
          :scroll-x="props.embedded ? 640 : 760"
          remote
          @update:sorter="handleSorterChange"
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
      :style="{
        width: 'min(960px, calc(100vw - 32px))',
        maxHeight: 'calc(100vh - 32px)',
      }"
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
            <RemoteModelPicker
              v-model="formModel.model_id"
              :active="showModal"
              :compatible-view-ids="selectedDatasetViewTypes"
              @update:selected-model="selectedModelRecord = $event"
            />
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
import { refDebounced } from "@vueuse/core";
import { useQuery, useQueryClient } from "@tanstack/vue-query";
import type {
  DataTableColumns,
  DataTableSortState,
  FormInst,
  FormRules,
  PaginationProps,
  SelectOption,
} from "naive-ui";
import { useMessage, NButton, NTag, NText } from "naive-ui";
import { useOrgStore } from "@/features/auth/application/org";
import { useAuthStore } from "@/features/auth/application/store";
import {
  useListPredictionJobsApiV1PredictionJobsGet,
  useRunPredictionsApiV1PredictionsRunPost,
} from "@/generated/orval/endpoints/api";
import { listDatasets } from "@/shared/api/datasets";
import { orgScopedQueryKey, toUserMessage } from "@/shared/api";
import TaskInsightModal, { TASK_INSIGHT_ORG_ID_KEY } from "@/shared/components/task-insight-modal";
import type {
  JobStatus,
  ListPredictionJobsApiV1PredictionJobsGetParams,
  ModelResponse,
  PredictionJobResponse as PredictionJob,
  TaskTrackerSummaryResponse as TaskTrackerSummary,
} from "@/generated/orval/models";
import type { RunPredictionRequest } from "@/generated/orval/models";
import RemoteModelPicker from "@/features/models/presentation/components/RemoteModelPicker.vue";
import CreatorScopeSelect from "@/shared/components/creator-scope-select";

const props = withDefaults(
  defineProps<{
    datasetId?: string | null;
    compatibleViewTypes?: string[];
    embedded?: boolean;
  }>(),
  { compatibleViewTypes: () => [], embedded: false },
);

const message = useMessage();
const qc = useQueryClient();
const orgStore = useOrgStore();
const authStore = useAuthStore();
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

const jobsPaginationState = reactive<PaginationProps>({
  page: 1,
  pageSize: 20,
  itemCount: 0,
  showSizePicker: true,
  pageSizes: [10, 20, 50, 100],
  onUpdatePage: (page: number) => {
    jobsPaginationState.page = page;
  },
  onUpdatePageSize: (pageSize: number) => {
    jobsPaginationState.pageSize = pageSize;
    jobsPaginationState.page = 1;
  },
});
const jobSearch = ref("");
const debouncedJobSearch = refDebounced(jobSearch, 250);
const statusFilter = ref<JobStatus | null>(null);
const creatorScope = ref("me");
const jobSorter = ref<DataTableSortState | null>({
  columnKey: "created_at",
  order: "descend",
  sorter: true,
});
const jobCreatorId = computed(() =>
  creatorScope.value === "all" ? undefined : authStore.user?.id,
);
const jobsParams = computed<ListPredictionJobsApiV1PredictionJobsGetParams>(() => ({
  dataset_id: props.datasetId ?? undefined,
  q: debouncedJobSearch.value.trim() || undefined,
  status: statusFilter.value ?? undefined,
  creator_id: jobCreatorId.value,
  sort_by:
    jobSorter.value?.columnKey === "updated_at" ||
    jobSorter.value?.columnKey === "status" ||
    jobSorter.value?.columnKey === "creator"
      ? jobSorter.value.columnKey
      : "created_at",
  sort_order: jobSorter.value?.order === "ascend" ? "asc" : "desc",
  offset: ((jobsPaginationState.page ?? 1) - 1) * (jobsPaginationState.pageSize ?? 20),
  limit: jobsPaginationState.pageSize ?? 20,
}));
const jobsQuery = useListPredictionJobsApiV1PredictionJobsGet(jobsParams, {
  query: {
    queryKey: computed(() =>
      orgScopedQueryKey(orgStore.currentOrgId, ["prediction-jobs", jobsParams.value]),
    ),
    refetchInterval: 5000,
    enabled: computed(() => !!orgStore.currentOrgId),
  },
});
const isLoading = computed(() => jobsQuery.isLoading.value);
const visibleJobs = computed<PredictionJob[]>(() => jobsQuery.data.value?.items ?? []);
const jobsPagination = computed(() => jobsPaginationState);

watch(
  () => jobsQuery.data.value?.total ?? 0,
  (total) => {
    jobsPaginationState.itemCount = total;
  },
  { immediate: true },
);
watch([debouncedJobSearch, statusFilter, creatorScope], () => {
  jobsPaginationState.page = 1;
});

const statusOptions = ["queued", "running", "completed", "failed", "cancelled"].map((status) => ({
  label: status.replace(/^./, (value) => value.toUpperCase()),
  value: status,
}));
const activeFilterCount = computed(
  () =>
    Number(jobSearch.value.trim().length > 0) +
    Number(statusFilter.value !== null) +
    Number(creatorScope.value !== "all"),
);

function clearFilters(): void {
  jobSearch.value = "";
  statusFilter.value = null;
  creatorScope.value = "all";
}

function handleSorterChange(value: DataTableSortState | DataTableSortState[] | null): void {
  jobSorter.value = Array.isArray(value) ? (value[0] ?? null) : value;
  jobsPaginationState.page = 1;
}

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

const selectedDatasetViewTypes = computed(() => {
  if (props.datasetId) return props.compatibleViewTypes;
  return (
    (datasets.value ?? []).find((dataset) => dataset.id === formModel.value.dataset_id)
      ?.view_types ?? []
  );
});

function predictionJobRowKey(row: PredictionJob): string {
  return row.id;
}

const selectedModelRecord = ref<ModelResponse | null>(null);
const selectedModel = computed(() => selectedModelRecord.value);

function modelDisplayName(model: ModelResponse): string {
  return model.name?.trim() || model.id.slice(0, 8);
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

function statusLabel(status: string): string {
  return status.replace(/_/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

const columns = computed<DataTableColumns<PredictionJob>>(() => {
  const baseColumns: DataTableColumns<PredictionJob> = [
    {
      title: "ID",
      key: "id",
      width: 120,
      render: (row) => h(NText, { title: row.id }, { default: () => `${row.id.slice(0, 8)}…` }),
    },
    {
      title: "Status",
      key: "status",
      width: 130,
      sorter: true,
      sortOrder: jobSorter.value?.columnKey === "status" ? jobSorter.value.order : false,
      render: (row) =>
        h(
          NTag,
          { type: statusType(row.status), size: "small", round: true },
          { default: () => statusLabel(row.status) },
        ),
    },
    {
      title: "Dataset ID",
      key: "dataset_id",
      ellipsis: { tooltip: true },
      render: (row) =>
        row.dataset_id
          ? h(
              NText,
              { title: row.dataset_id },
              { default: () => `${row.dataset_id?.slice(0, 8)}…` },
            )
          : "Deleted dataset",
    },
    {
      title: "Model ID",
      key: "model_id",
      ellipsis: { tooltip: true },
      render: (row) =>
        h(NText, { title: row.model_id }, { default: () => `${row.model_id.slice(0, 8)}…` }),
    },
    {
      title: "Creator",
      key: "creator",
      width: 150,
      sorter: true,
      sortOrder: jobSorter.value?.columnKey === "creator" ? jobSorter.value.order : false,
      render: (row) => (row.created_by === authStore.user?.id ? "You" : row.created_by || "system"),
    },
    {
      title: "Created At",
      key: "created_at",
      width: 180,
      sorter: true,
      sortOrder: jobSorter.value?.columnKey === "created_at" ? jobSorter.value.order : false,
      render: (row) => new Date(row.created_at).toLocaleString(),
    },
    {
      title: "Actions",
      key: "actions",
      width: 150,
      fixed: "right",
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
  formRef.value?.restoreValidation();
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

.history-filters {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) 170px 210px auto;
  gap: 8px;
  align-items: center;
}

.history-creator-filter {
  min-width: 0;
}

@media (max-width: 640px) {
  .embedded-section-header {
    align-items: stretch;
    flex-direction: column;
  }

  .embedded-section-header :deep(.n-button) {
    width: 100%;
  }

  .history-filters {
    grid-template-columns: 1fr;
  }
}
</style>
