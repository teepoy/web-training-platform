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

      <ResourceFilterBar
        :keyword="jobSearch"
        keyword-placeholder="Search jobs"
        :creator-scope="creatorScope"
        :creators="[]"
        :active-filter-count="activeFilterCount"
        resource-label="training jobs"
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
        :data="jobsItems"
        :pagination="jobsPagination"
        :bordered="true"
        :striped="true"
        :loading="isLoading"
        :error="jobsErrorMessage"
        :active-filter-count="activeFilterCount"
        :empty-description="
          props.datasetId ? 'No training runs for this dataset yet' : 'No training runs yet'
        "
        no-results-description="No training runs match these filters"
        :scroll-x="props.embedded ? 820 : 980"
        remote
        @update:sorter="handleSorterChange"
      />

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
          <n-form-item v-if="!props.datasetId" label="Target" path="target">
            <ResourceTargetSelect v-model="formModel.target" :active="showModal" />
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
import { ref, computed, h, provide, watch } from "vue";
import type { MaybeRef } from "vue";
import { useRouter } from "vue-router";
import { useQueryClient } from "@tanstack/vue-query";
import type { DataTableColumns, FormInst, FormRules, SelectOption } from "naive-ui";
import { useMessage, NButton, NTag } from "naive-ui";
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
  CreateTrainingJobRequest,
  JobStatus,
  TaskTrackerSummaryResponse as TaskTrackerSummary,
  TrainingJob,
} from "@/generated/orval/models";
import type { Trainer } from "@/shared/api/types";
import TaskInsightModal, { TASK_INSIGHT_ORG_ID_KEY } from "@/shared/components/task-insight-modal";
import RemoteListTableShell from "@/shared/components/remote-list-table-shell";
import ResourceFilterBar from "@/shared/components/resource-filter-bar";
import ResourceTargetLink from "@/shared/components/resource-target-link";
import ResourceTargetSelect, {
  resourceTargetRequestFields,
  type ResourceTargetSelection,
} from "@/shared/components/resource-target-select";
import StatusBadge from "@/shared/components/status-badge";
import { useRemoteListState } from "@/shared/composables/useRemoteListState";

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
const { debouncedKeyword: debouncedJobSearch, pagination: jobsPagination, sorter } = listState;
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
  offset: ((jobsPagination.page ?? 1) - 1) * (jobsPagination.pageSize ?? 20),
  limit: jobsPagination.pageSize ?? 20,
})) as MaybeRef<ListJobsApiV1TrainingJobsGetParams>;

const {
  data: jobsPage,
  isLoading,
  error: jobsError,
} = useListJobsApiV1TrainingJobsGet(jobsQueryParams, {
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
        jobsPagination.page,
        jobsPagination.pageSize,
      ]),
    ),
    refetchInterval: 5000,
    enabled: computed(() => !!orgStore.currentOrgId),
  },
});
const jobsItems = computed(() =>
  jobsPage.value && "items" in jobsPage.value ? jobsPage.value.items : [],
);
watch(
  () => (jobsPage.value && "total" in jobsPage.value ? jobsPage.value.total : 0),
  (total) => {
    jobsTotal.value = total;
  },
  { immediate: true },
);
const jobsErrorMessage = computed(() =>
  jobsError.value ? toUserMessage(jobsError.value, "Failed to load training runs") : null,
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

const compatibleTrainerViewTypes = computed(
  () => props.compatibleViewTypes ?? formModel.value.target?.viewTypes ?? [],
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
      render: (row) => h(StatusBadge, { status: row.status ?? "queued" }),
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
const formModel = ref({
  target: null as ResourceTargetSelection | null,
  trainer_id: null as string | null,
});

const formRules: FormRules = {
  target: [{ required: true, message: "Please select a target", trigger: ["blur", "change"] }],
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
    if ((!props.datasetId && !formModel.value.target) || !formModel.value.trainer_id) return;
    const target = formModel.value.target;
    const data: CreateTrainingJobRequest = {
      trainer_id: formModel.value.trainer_id,
      ...(props.datasetId
        ? { dataset_id: props.datasetId }
        : target
          ? resourceTargetRequestFields(target)
          : {}),
    };
    createJobMutation.mutate({
      data,
    });
  });
  return false;
}

function onCancel() {
  resetForm();
}

function resetForm() {
  formModel.value = { target: null, trainer_id: null };
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
