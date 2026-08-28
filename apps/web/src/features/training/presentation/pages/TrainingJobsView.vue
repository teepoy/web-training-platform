<template>
  <n-space vertical size="large">
    <template v-if="!orgStore.currentOrgId">
      <div style="padding: 48px; text-align: center">
        <n-empty description="You are not a member of any organization. Contact an admin." />
      </div>
    </template>
    <template v-else>
      <n-page-header v-if="!props.embedded" title="Training Jobs">
        <template #extra>
          <n-button type="primary" :disabled="!canTrain" @click="showModal = true"
            >Start New Job</n-button
          >
        </template>
      </n-page-header>
      <div v-else class="embedded-section-header">
        <div>
          <n-h3 class="embedded-section-title">Training runs</n-h3>
          <n-text depth="3">Train this dataset and review its recent runs.</n-text>
        </div>
        <n-button type="primary" :disabled="!canTrain" @click="showModal = true">
          Start New Job
        </n-button>
      </div>

      <n-alert v-if="!canTrain && effectiveTrainDisabledReason" type="warning">
        {{ effectiveTrainDisabledReason }}
      </n-alert>

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
          resource-label="training jobs"
          class="history-creator-filter"
        />
        <n-button v-if="activeFilterCount > 0" size="small" quaternary @click="clearFilters">
          Clear filters ({{ activeFilterCount }})
        </n-button>
      </div>

      <n-spin :show="isLoading">
        <n-data-table
          :columns="columns"
          :data="jobsItems"
          :pagination="jobsPagination"
          :bordered="true"
          :striped="true"
          :loading="isLoading"
          :scroll-x="props.embedded ? 820 : 980"
          remote
          @update:sorter="handleSorterChange"
        >
          <template #empty>
            <n-empty
              :description="
                props.datasetId ? 'No training runs for this dataset yet' : 'No training runs yet'
              "
            />
          </template>
        </n-data-table>
      </n-spin>

      <n-modal
        v-model:show="showModal"
        preset="dialog"
        title="Start New Job"
        positive-text="Start"
        negative-text="Cancel"
        :loading="createJobMutation.isPending.value"
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
          <n-form-item v-if="!props.datasetId" label="Dataset" path="dataset_id">
            <n-select
              v-model:value="formModel.dataset_id"
              :options="datasetOptions"
              :loading="datasetsLoading"
              placeholder="Select a dataset"
              filterable
            />
          </n-form-item>
          <n-form-item label="Trainer" path="trainer_id">
            <template v-if="props.datasetId && !trainersLoading && trainerOptions.length === 0">
              <n-empty description="No compatible trainer for this dataset" />
            </template>
            <n-select
              v-else
              v-model:value="formModel.trainer_id"
              :options="trainerOptions"
              :loading="trainersLoading"
              placeholder="Select a trainer"
              filterable
            />
          </n-form-item>
        </n-form>
      </n-modal>

      <TaskInsightModal
        v-model:show="insightVisible"
        :task="selectedTask"
        :handoff-enabled="false"
      />
    </template>
  </n-space>
</template>

<script setup lang="ts">
import { ref, computed, h, provide, reactive, watch } from "vue";
import { refDebounced } from "@vueuse/core";
import type { MaybeRef } from "vue";
import { useRouter } from "vue-router";
import { useQuery, useQueryClient } from "@tanstack/vue-query";
import type {
  DataTableColumns,
  DataTableSortState,
  FormInst,
  FormRules,
  PaginationProps,
  SelectOption,
} from "naive-ui";
import { useMessage, NTag, NButton } from "naive-ui";
import { listDatasets } from "@/shared/api/datasets";
import { orgScopedQueryKey, toUserMessage } from "@/shared/api";
import { useOrgStore } from "@/features/auth/application/org";
import { useAuthStore } from "@/features/auth/application/store";
import {
  useListJobsApiV1TrainingJobsGet,
  useCreateTrainingJobApiV1TrainingJobsPost,
  useListTrainersRouteApiV1TrainersGet,
} from "@/generated/orval/endpoints/api";
import type { ListJobsApiV1TrainingJobsGetParams } from "@/generated/orval/models/listJobsApiV1TrainingJobsGetParams";
import type {
  JobStatus,
  TaskTrackerSummaryResponse as TaskTrackerSummary,
  TrainingJob,
} from "@/generated/orval/models";
import type { Trainer } from "@/shared/api/types";
import TaskInsightModal, { TASK_INSIGHT_ORG_ID_KEY } from "@/shared/components/task-insight-modal";
import CreatorScopeSelect from "@/shared/components/creator-scope-select";

const router = useRouter();
const message = useMessage();
const qc = useQueryClient();
const orgStore = useOrgStore();
const authStore = useAuthStore();
const props = withDefaults(
  defineProps<{
    datasetId?: string | null;
    allowTrain?: boolean;
    trainDisabledReason?: string | null;
    compatibleViewTypes?: string[] | null;
    embedded?: boolean;
  }>(),
  { allowTrain: true, embedded: false },
);
const jobsQueryPrefix = computed(() => orgScopedQueryKey(orgStore.currentOrgId, ["jobs"]));
provide(
  TASK_INSIGHT_ORG_ID_KEY,
  computed(() => orgStore.currentOrgId),
);

const jobsPageNumber = ref(1);
const jobsPageSize = ref(20);
const jobSearch = ref("");
const debouncedJobSearch = refDebounced(jobSearch, 250);
const statusFilter = ref<JobStatus | null>(null);
const creatorScope = ref("me");
const sorter = ref<DataTableSortState | null>({
  columnKey: "created_at",
  order: "descend",
  sorter: true,
});
const creatorId = computed(() => {
  if (creatorScope.value === "all") return undefined;
  return authStore.user?.id;
});
const jobsQueryParams = computed(() => ({
  dataset_id: props.datasetId ?? undefined,
  q: debouncedJobSearch.value.trim() || undefined,
  status: statusFilter.value ?? undefined,
  creator_id: creatorId.value,
  sort_by:
    sorter.value?.columnKey === "updated_at" ||
    sorter.value?.columnKey === "status" ||
    sorter.value?.columnKey === "creator"
      ? sorter.value.columnKey
      : ("created_at" as const),
  sort_order: sorter.value?.order === "ascend" ? ("asc" as const) : ("desc" as const),
  offset: (jobsPageNumber.value - 1) * jobsPageSize.value,
  limit: jobsPageSize.value,
})) as MaybeRef<ListJobsApiV1TrainingJobsGetParams>;

const { data: jobsPage, isLoading } = useListJobsApiV1TrainingJobsGet(jobsQueryParams, {
  query: {
    queryKey: computed(() =>
      orgScopedQueryKey(orgStore.currentOrgId, [
        "jobs",
        props.datasetId,
        debouncedJobSearch.value.trim(),
        statusFilter.value,
        creatorId.value,
        sorter.value?.columnKey,
        sorter.value?.order,
        jobsPageNumber.value,
        jobsPageSize.value,
      ]),
    ),
    refetchInterval: 5000,
    enabled: computed(() => !!orgStore.currentOrgId),
  },
});
const jobsItems = computed(() =>
  jobsPage.value && "items" in jobsPage.value ? jobsPage.value.items : [],
);
const jobsTotal = computed(() =>
  jobsPage.value && "total" in jobsPage.value ? jobsPage.value.total : 0,
);
const jobsPagination = computed(() => {
  const pagination: PaginationProps = {
    page: jobsPageNumber.value,
    pageSize: jobsPageSize.value,
    itemCount: jobsTotal.value,
    showSizePicker: true,
    pageSizes: [10, 20, 50, 100],
    onUpdatePage: (page: number) => {
      jobsPageNumber.value = page;
    },
    onUpdatePageSize: (pageSize: number) => {
      jobsPageSize.value = pageSize;
      jobsPageNumber.value = 1;
    },
  };
  return pagination;
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

watch([debouncedJobSearch, statusFilter, creatorScope], () => {
  jobsPageNumber.value = 1;
});

function clearFilters(): void {
  jobSearch.value = "";
  statusFilter.value = null;
  creatorScope.value = "all";
}

function handleSorterChange(value: DataTableSortState | DataTableSortState[] | null): void {
  sorter.value = Array.isArray(value) ? (value[0] ?? null) : value;
  jobsPageNumber.value = 1;
}

const { data: datasets, isLoading: datasetsLoading } = useQuery({
  queryKey: computed(() => orgScopedQueryKey(orgStore.currentOrgId, ["datasets", "all-pages"])),
  queryFn: listDatasets,
  enabled: computed(() => !!orgStore.currentOrgId && !props.datasetId),
});

const { data: trainers, isLoading: trainersLoading } = useListTrainersRouteApiV1TrainersGet({
  query: {
    select: (response) =>
      response.map(
        (item): Trainer => ({
          id: String(item.id ?? ""),
          name: String(item.name ?? ""),
          view_type: String(item.view_type ?? ""),
          trainable: Boolean(item.trainable ?? true),
        }),
      ),
    queryKey: computed(() => orgScopedQueryKey(orgStore.currentOrgId, ["trainers"])),
    refetchInterval: 30000,
    enabled: computed(() => !!orgStore.currentOrgId),
  },
});

const datasetOptions = computed<SelectOption[]>(() =>
  (datasets.value ?? []).map((d) => ({ label: d.name, value: d.id })),
);

const selectedDataset = computed(() =>
  (datasets.value ?? []).find((d) => d.id === formModel.value.dataset_id),
);

const compatibleTrainerViewTypes = computed(
  () => props.compatibleViewTypes ?? selectedDataset.value?.view_types ?? [],
);

const trainerOptions = computed<SelectOption[]>(() =>
  (trainers.value ?? [])
    .filter((t) => t.trainable !== false)
    .filter((t) => {
      if (!compatibleTrainerViewTypes.value.length) return true;
      if (!hasTrainerViewType(t)) return false;
      return compatibleTrainerViewTypes.value.includes(t.view_type);
    })
    .map((t) => ({ label: t.name, value: t.id })),
);

const canTrain = computed(() => props.allowTrain);
const effectiveTrainDisabledReason = computed(() => props.trainDisabledReason ?? null);

function hasTrainerViewType(trainer: Trainer): trainer is Trainer & { view_type: string } {
  return typeof (trainer as { view_type?: unknown }).view_type === "string";
}

type TagType = "default" | "info" | "success" | "error" | "warning";

function statusType(status: JobStatus): TagType {
  const map: Record<JobStatus, TagType> = {
    queued: "default",
    running: "info",
    completed: "success",
    failed: "error",
    cancelled: "warning",
  };
  return map[status] ?? "default";
}

const columns = computed<DataTableColumns<TrainingJob>>(() => {
  const baseColumns: DataTableColumns<TrainingJob> = [
    {
      title: "ID",
      key: "id",
      width: 120,
      render: (row) => (row.id ?? "").slice(0, 8) + "…",
    },
    {
      title: "Status",
      key: "status",
      width: 130,
      sorter: true,
      sortOrder: sorter.value?.columnKey === "status" ? sorter.value.order : false,
      render: (row) =>
        h(
          NTag,
          { type: statusType(row.status!), size: "small", round: true },
          { default: () => row.status },
        ),
    },
    {
      title: "Public",
      key: "is_public",
      width: 160,
      render: (row) => {
        const nodes = [];
        if (row.is_public) {
          nodes.push(h(NTag, { type: "info", size: "small" }, { default: () => "Public" }));
        }
        if (row.is_public && row.org_id !== orgStore.currentOrgId) {
          nodes.push(
            h(
              "span",
              { style: "margin-left: 4px; font-size: 12px; color: #aaa" },
              `(${row.org_name ?? "Other Org"})`,
            ),
          );
        }
        return h("span", {}, nodes);
      },
    },
    {
      title: "Dataset ID",
      key: "dataset_id",
      ellipsis: { tooltip: true },
      render: (row) => (row.dataset_id ? row.dataset_id.slice(0, 8) + "…" : "Deleted dataset"),
    },
    {
      title: "Trainer",
      key: "trainer_id",
      ellipsis: { tooltip: true },
      render: (row) => row.trainer_id,
    },
    {
      title: "Creator",
      key: "creator",
      width: 150,
      sorter: true,
      sortOrder: sorter.value?.columnKey === "creator" ? sorter.value.order : false,
      render: (row) => (row.created_by === authStore.user?.id ? "You" : row.created_by || "system"),
    },
    {
      title: "Created At",
      key: "created_at",
      width: 180,
      sorter: true,
      sortOrder: sorter.value?.columnKey === "created_at" ? sorter.value.order : false,
      render: (row) => new Date(row.created_at!).toLocaleString(),
    },
    {
      title: "Actions",
      key: "actions",
      width: 220,
      render: (row) => {
        const nodes = [
          h(
            NButton,
            {
              size: "small",
              disabled: !row.id,
              onClick: (e: Event) => {
                e.stopPropagation();
                openJobDetail(row);
              },
            },
            { default: () => "View" },
          ),
          h(
            NButton,
            {
              size: "small",
              tertiary: true,
              disabled: !row.id,
              onClick: (e: Event) => {
                e.stopPropagation();
                openInsight(row);
              },
            },
            { default: () => "Task Progress" },
          ),
        ];
        return h("span", { style: "display: inline-flex; gap: 8px" }, nodes);
      },
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
const formModel = ref({ dataset_id: null as string | null, trainer_id: null as string | null });

watch(
  () => props.datasetId,
  (val) => {
    formModel.value.dataset_id = val ?? null;
  },
  { immediate: true },
);

const formRules: FormRules = {
  dataset_id: [{ required: true, message: "Please select a dataset", trigger: ["blur", "change"] }],
  trainer_id: [{ required: true, message: "Please select a trainer", trigger: ["blur", "change"] }],
};

const createJobMutation = useCreateTrainingJobApiV1TrainingJobsPost({
  mutation: {
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: jobsQueryPrefix.value });
      message.success("Job started");
      showModal.value = false;
      resetForm();
    },
    onError: (error) => {
      message.error(toUserMessage(error, "Failed to start job"));
    },
  },
});

function onSubmit() {
  formRef.value?.validate((errors) => {
    if (errors) return;
    if (!formModel.value.dataset_id || !formModel.value.trainer_id) return;
    createJobMutation.mutate({
      data: {
        dataset_id: formModel.value.dataset_id!,
        trainer_id: formModel.value.trainer_id!,
      },
    });
  });
  return false;
}

function onCancel() {
  resetForm();
}

function resetForm() {
  formModel.value = { dataset_id: props.datasetId ?? null, trainer_id: null };
  formRef.value?.restoreValidation();
}

function openJobDetail(row: TrainingJob) {
  if (!row.id) return;
  router.push(`/jobs/${row.id}`);
}

function openInsight(row: TrainingJob) {
  if (!row.id) return;
  selectedTask.value = trainingTaskSummary(row);
  insightVisible.value = true;
}

function trainingTaskSummary(row: TrainingJob): TaskTrackerSummary {
  return {
    id: row.id ?? "",
    task_kind: "training",
    execution_kind: "training-default",
    display_name: `Training ${row.trainer_id}`,
    display_status: row.status ?? "queued",
    stage:
      row.status === "completed" || row.status === "failed"
        ? "validation_output"
        : "queue_allocation",
    dataset_id: row.dataset_id,
    model_id: null,
    trainer_id: row.trainer_id,
    created_by: row.created_by,
    created_at: row.created_at ?? "",
    updated_at: row.updated_at ?? row.created_at ?? "",
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
