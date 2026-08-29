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
      <ResourceFilterBar
        :keyword="jobSearch"
        keyword-placeholder="Search jobs"
        :creator-scope="creatorScope"
        :creators="[]"
        :active-filter-count="activeFilterCount"
        resource-label="prediction jobs"
        @update:keyword="jobSearch = $event"
        @update:creator-scope="creatorScope = $event"
        @clear="clearFilters"
      >
        <template #filters>
          <n-select
            v-model:value="statusFilter"
            clearable
            size="small"
            :options="statusOptions"
            placeholder="All statuses"
            class="history-status-filter"
          />
        </template>
      </ResourceFilterBar>
      <RemoteListTableShell
        :columns="columns"
        :data="visibleJobs"
        :bordered="true"
        :striped="true"
        :loading="isLoading"
        :error="jobsErrorMessage"
        :active-filter-count="activeFilterCount"
        :pagination="jobsPagination"
        :row-key="predictionJobRowKey"
        :empty-description="
          props.datasetId ? 'No prediction runs for this dataset yet' : 'No prediction runs yet'
        "
        no-results-description="No prediction runs match these filters"
        :scroll-x="props.embedded ? 640 : 760"
        remote
        @update:sorter="handleSorterChange"
      />
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
          <n-form-item v-if="!props.datasetId" label="Target" path="target">
            <ResourceTargetSelect v-model="formModel.target" :active="showModal" />
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
              :disabled="!formModel.model_id || (!props.datasetId && !formModel.target)"
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
import { ref, computed, h, provide, watch } from "vue";
import { useQueryClient } from "@tanstack/vue-query";
import type { DataTableColumns, FormInst, FormRules } from "naive-ui";
import { useMessage, NButton, NText } from "naive-ui";
import { useOrgStore } from "@/features/auth/application/org";
import { useAuthStore } from "@/features/auth/application/store";
import {
  useListPredictionJobsApiV1PredictionJobsGet,
  useRunPredictionsApiV1PredictionsRunPost,
} from "@/generated/orval/endpoints/api";
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
import RemoteListTableShell from "@/shared/components/remote-list-table-shell";
import ResourceFilterBar from "@/shared/components/resource-filter-bar";
import ResourceTargetLink from "@/shared/components/resource-target-link";
import ResourceTargetSelect, {
  resourceTargetRequestFields,
  type ResourceTargetSelection,
} from "@/shared/components/resource-target-select";
import StatusBadge from "@/shared/components/status-badge";
import { useRemoteListState } from "@/shared/composables/useRemoteListState";

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
  target: null as ResourceTargetSelection | null,
  model_id: null as string | null,
});
provide(
  TASK_INSIGHT_ORG_ID_KEY,
  computed(() => orgStore.currentOrgId),
);

const jobSearch = ref("");
const statusFilter = ref<JobStatus | null>(null);
const creatorScope = ref("me");
const jobsTotal = ref(0);
const listState = useRemoteListState({
  keyword: jobSearch,
  filters: [statusFilter, creatorScope],
  total: jobsTotal,
  initialSorter: { columnKey: "created_at", order: "descend", sorter: true },
});
const {
  debouncedKeyword: debouncedJobSearch,
  pagination: jobsPagination,
  sorter: jobSorter,
} = listState;
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
  offset: ((jobsPagination.page ?? 1) - 1) * (jobsPagination.pageSize ?? 20),
  limit: jobsPagination.pageSize ?? 20,
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
const jobsErrorMessage = computed(() =>
  jobsQuery.error.value
    ? toUserMessage(jobsQuery.error.value, "Failed to load prediction runs")
    : null,
);

watch(
  () => jobsQuery.data.value?.total ?? 0,
  (total) => {
    jobsTotal.value = total;
  },
  { immediate: true },
);

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

const handleSorterChange = listState.handleSorterChange;

const selectedDatasetViewTypes = computed(() => {
  if (props.datasetId) return props.compatibleViewTypes;
  return formModel.value.target?.viewTypes ?? [];
});

function predictionJobRowKey(row: PredictionJob): string {
  return row.id;
}

const selectedModelRecord = ref<ModelResponse | null>(null);
const selectedModel = computed(() => selectedModelRecord.value);

function modelDisplayName(model: ModelResponse): string {
  return model.name?.trim() || model.id.slice(0, 8);
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
      render: (row) => h(StatusBadge, { status: row.status }),
    },
    {
      title: "Target",
      key: "dataset_id",
      ellipsis: { tooltip: true },
      render: (row) =>
        h(ResourceTargetLink, {
          datasetId: row.dataset_id,
          collectionId: row.collection_id,
          collectionRevisionId: row.collection_revision_id,
        }),
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

const formRules: FormRules = {
  target: [{ required: true, message: "Please select a target", trigger: ["change"] }],
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
    if (!formModel.value.model_id || (!props.datasetId && !formModel.value.target)) return;
    const target = formModel.value.target;

    const request: RunPredictionRequest = {
      model_id: formModel.value.model_id,
      ...(props.datasetId
        ? { dataset_id: props.datasetId }
        : target
          ? resourceTargetRequestFields(target)
          : {}),
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
  formModel.value = { target: null, model_id: null };
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

.history-status-filter {
  width: min(180px, 100%);
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
