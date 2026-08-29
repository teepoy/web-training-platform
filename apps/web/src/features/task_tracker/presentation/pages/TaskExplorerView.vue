<template>
  <n-space vertical size="large">
    <n-page-header :title="t('tasks.title')">
      <template #extra>
        <n-button size="small" :loading="isFetching" @click="handleRefresh">
          {{ t("automations.refresh") }}
        </n-button>
      </template>
    </n-page-header>
    <div class="task-filters">
      <n-input v-model:value="search" clearable size="small" :placeholder="t('tasks.search')" />
      <n-select
        :value="taskKind"
        clearable
        size="small"
        :options="kindOptions"
        :placeholder="t('tasks.allKinds')"
        @update:value="setTaskKind"
      />
      <n-select
        v-model:value="statusFilter"
        clearable
        size="small"
        :options="statusOptions"
        :placeholder="t('tasks.allStatuses')"
      />
      <CreatorScopeSelect
        v-model="creatorScope"
        :creators="[]"
        :resource-label="t('tasks.resourceLabel')"
        class="task-creator-filter"
      />
      <n-button v-if="activeFilterCount > 0" size="small" quaternary @click="clearFilters">
        {{ t("common.clearFilters", { count: activeFilterCount }) }}
      </n-button>
    </div>
    <n-spin :show="isLoading">
      <n-data-table
        :columns="columns"
        :data="tasks"
        :row-key="taskRowKey"
        :bordered="true"
        :striped="true"
        :loading="isLoading"
        :pagination="pagination"
        remote
        @update:sorter="handleSorterChange"
      />
    </n-spin>
    <TaskInsightModal v-model:show="insightVisible" :task="selectedTask" :handoff-enabled="false" />
  </n-space>
</template>

<script setup lang="ts">
import { computed, h, provide, reactive, ref, watch } from "vue";
import { refDebounced } from "@vueuse/core";
import { useRoute, useRouter } from "vue-router";
import type { DataTableColumns, DataTableSortState, PaginationProps } from "naive-ui";
import { NButton, NTag } from "naive-ui";
import { useI18n } from "vue-i18n";
import { useOrgStore } from "@/features/auth/application/org";
import { useAuthStore } from "@/features/auth/application/store";
import { useTrackedTasksQuery } from "@/shared/api/hooks/task-tracker";
import TaskInsightModal, { TASK_INSIGHT_ORG_ID_KEY } from "@/shared/components/task-insight-modal";
import type { TaskTrackerSummaryResponse as TaskTrackerSummary } from "@/generated/orval/models";
import type {
  JobStatus,
  ListTaskTrackerTasksApiV1TaskTrackerTasksGetParams,
} from "@/generated/orval/models";
import CreatorScopeSelect from "@/shared/components/creator-scope-select";
import { orgScopedQueryKey } from "@/shared/api";
import { formatDateTime } from "@/shared/i18n/format";

const route = useRoute();
const { t } = useI18n();
const router = useRouter();
const orgStore = useOrgStore();
const authStore = useAuthStore();
provide(
  TASK_INSIGHT_ORG_ID_KEY,
  computed(() => orgStore.currentOrgId),
);

type TaskKind = "training" | "prediction" | "schedule_run";

const taskKind = computed<TaskKind | undefined>(() => {
  const raw = route.query.kind;
  const value = Array.isArray(raw) ? raw[0] : raw;
  return value === "training" || value === "prediction" || value === "schedule_run"
    ? value
    : undefined;
});

const search = ref("");
const debouncedSearch = refDebounced(search, 250);
const statusFilter = ref<JobStatus | null>(null);
const creatorScope = ref("me");
const sortOrder = ref<"asc" | "desc">("desc");
const paginationState = reactive<PaginationProps>({
  page: 1,
  pageSize: 20,
  itemCount: 0,
  showSizePicker: true,
  pageSizes: [10, 20, 50, 100],
  onUpdatePage: (page: number) => {
    paginationState.page = page;
  },
  onUpdatePageSize: (pageSize: number) => {
    paginationState.pageSize = pageSize;
    paginationState.page = 1;
  },
});
const creatorId = computed(() => (creatorScope.value === "all" ? undefined : authStore.user?.id));
const queryParams = computed<ListTaskTrackerTasksApiV1TaskTrackerTasksGetParams>(() => ({
  kind: taskKind.value,
  q: debouncedSearch.value.trim() || undefined,
  status: statusFilter.value ?? undefined,
  creator_id: creatorId.value,
  sort_order: sortOrder.value,
  offset: ((paginationState.page ?? 1) - 1) * (paginationState.pageSize ?? 20),
  limit: paginationState.pageSize ?? 20,
}));
const tasksQuery = useTrackedTasksQuery(queryParams, {
  queryKey: computed(() =>
    orgScopedQueryKey(orgStore.currentOrgId, ["task-tracker", queryParams.value]),
  ),
  enabled: computed(() => !!orgStore.currentOrgId),
  refetchInterval: false,
});
const tasks = computed(() => tasksQuery.data.value?.items ?? []);
const isLoading = computed(() => tasksQuery.isLoading.value);
const isFetching = computed(() => tasksQuery.isFetching.value);
const pagination = computed(() => paginationState);

watch(
  () => tasksQuery.data.value?.total ?? 0,
  (total) => {
    paginationState.itemCount = total;
  },
  { immediate: true },
);
watch([debouncedSearch, statusFilter, creatorScope, taskKind], () => {
  paginationState.page = 1;
});

const kindOptions = computed(() => [
  { label: t("tasks.training"), value: "training" },
  { label: t("tasks.prediction"), value: "prediction" },
  { label: t("tasks.automationRun"), value: "schedule_run" },
]);
const statusOptions = computed(() =>
  ["queued", "running", "completed", "failed", "cancelled"].map((status) => ({
    label: t(`status.${status}`),
    value: status,
  })),
);
const activeFilterCount = computed(
  () =>
    Number(search.value.trim().length > 0) +
    Number(taskKind.value !== undefined) +
    Number(statusFilter.value !== null) +
    Number(creatorScope.value !== "all"),
);

function setTaskKind(value: TaskKind | null): void {
  const query = { ...route.query };
  if (value) query.kind = value;
  else delete query.kind;
  void router.replace({ query });
}

function clearFilters(): void {
  search.value = "";
  statusFilter.value = null;
  creatorScope.value = "all";
  setTaskKind(null);
}

function handleSorterChange(value: DataTableSortState | DataTableSortState[] | null): void {
  const sorter = Array.isArray(value) ? value[0] : value;
  sortOrder.value = sorter?.order === "ascend" ? "asc" : "desc";
  paginationState.page = 1;
}

const insightVisible = ref(false);
const selectedTask = ref<TaskTrackerSummary | null>(null);

function handleRefresh(): void {
  void tasksQuery.refetch();
}

function taskRowKey(row: TaskTrackerSummary): string {
  return row.id;
}

watch(
  () => [route.query.task, tasks.value] as const,
  ([taskQuery, currentTasks]) => {
    const taskId = Array.isArray(taskQuery) ? taskQuery[0] : taskQuery;
    if (!taskId) return;
    const task = currentTasks.find((item) => item.id === taskId);
    if (!task) return;
    selectedTask.value = task;
    insightVisible.value = true;
  },
  { immediate: true },
);

function openInsight(row: TaskTrackerSummary): void {
  selectedTask.value = row;
  insightVisible.value = true;
}

const columns = computed<DataTableColumns<TaskTrackerSummary>>(() => [
  { title: t("tasks.task"), key: "display_name", ellipsis: { tooltip: true } },
  {
    title: t("resources.dataset"),
    key: "dataset_name",
    width: 220,
    ellipsis: { tooltip: true },
    render: (row) => row.dataset_name || (row.dataset_id ? `${row.dataset_id.slice(0, 8)}…` : "—"),
  },
  {
    title: t("jobs.status"),
    key: "display_status",
    width: 140,
    render: (row) => h(NTag, { size: "small" }, { default: () => row.display_status }),
  },
  { title: t("tasks.stage"), key: "stage", width: 140 },
  { title: t("tasks.kind"), key: "task_kind", width: 120 },
  { title: t("tasks.queue"), key: "queue_priority_label", width: 140 },
  {
    title: t("tasks.updated"),
    key: "updated_at",
    width: 180,
    sorter: true,
    sortOrder: sortOrder.value === "asc" ? "ascend" : "descend",
    render: (row) => formatDateTime(row.updated_at),
  },
  {
    title: t("common.actions"),
    key: "actions",
    width: 110,
    render: (row) =>
      h(
        NButton,
        {
          size: "small",
          onClick: () => openInsight(row),
        },
        { default: () => t("tasks.insight") },
      ),
  },
]);
</script>

<style scoped>
.task-filters {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) 170px 170px 190px auto;
  gap: 8px;
  align-items: center;
}

.task-creator-filter {
  min-width: 0;
}

@media (max-width: 820px) {
  .task-filters {
    grid-template-columns: 1fr;
  }
}
</style>
