<template>
  <n-space vertical size="large">
    <n-page-header title="Task Explorer">
      <template #extra>
        <n-button size="small" :loading="isFetching" @click="handleRefresh">
          Refresh
        </n-button>
      </template>
    </n-page-header>
    <n-spin :show="isLoading">
      <n-data-table
        :columns="columns"
        :data="tasks ?? []"
        :row-key="taskRowKey"
        :bordered="true"
        :striped="true"
        :loading="isLoading"
      />
    </n-spin>
    <TaskInsightModal
      v-model:show="insightVisible"
      :task="selectedTask"
      :handoff-enabled="false"
    />
  </n-space>
</template>

<script setup lang="ts">
import { computed, h, provide, ref, watch } from "vue";
import { useRoute } from "vue-router";
import type { DataTableColumns } from "naive-ui";
import { NButton, NTag } from "naive-ui";
import { useOrgStore } from "@/features/auth/application/org";
import { useTrackedTasksQuery } from "@/shared/api/hooks/task-tracker";
import TaskInsightModal, { TASK_INSIGHT_ORG_ID_KEY } from "@/shared/components/task-insight-modal";
import type { TaskTrackerSummaryResponse as TaskTrackerSummary } from "@/generated/orval/models";

const route = useRoute();
const orgStore = useOrgStore();
provide(TASK_INSIGHT_ORG_ID_KEY, computed(() => orgStore.currentOrgId));

const taskKind = computed<"training" | "prediction" | undefined>(() => {
  const raw = route.query.kind;
  const value = Array.isArray(raw) ? raw[0] : raw;
  return value === "training" || value === "prediction" ? value : undefined;
});

const { data: tasks, isLoading, isFetching, refetch } = useTrackedTasksQuery(
  () => taskKind.value,
  { refetchInterval: false },
);

const insightVisible = ref(false);
const selectedTask = ref<TaskTrackerSummary | null>(null);

function handleRefresh(): void {
  void refetch();
}

function taskRowKey(row: TaskTrackerSummary): string {
  return row.id;
}

watch(
  () => [route.query.task, tasks.value] as const,
  ([taskQuery, currentTasks]) => {
    const taskId = Array.isArray(taskQuery) ? taskQuery[0] : taskQuery;
    if (!taskId || !currentTasks) return;
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
  { title: "Task", key: "display_name", ellipsis: { tooltip: true } },
  {
    title: "Dataset",
    key: "dataset_name",
    width: 220,
    ellipsis: { tooltip: true },
    render: (row) =>
      row.dataset_name || (row.dataset_id ? `${row.dataset_id.slice(0, 8)}…` : "—"),
  },
  {
    title: "Status",
    key: "display_status",
    width: 140,
    render: (row) => h(NTag, { size: "small" }, { default: () => row.display_status }),
  },
  { title: "Stage", key: "stage", width: 140 },
  { title: "Kind", key: "task_kind", width: 120 },
  { title: "Queue", key: "queue_priority_label", width: 140 },
  {
    title: "Updated",
    key: "updated_at",
    width: 180,
    render: (row) => new Date(row.updated_at).toLocaleString(),
  },
  {
    title: "Actions",
    key: "actions",
    width: 110,
    render: (row) =>
      h(
        NButton,
        {
          size: "small",
          onClick: () => openInsight(row),
        },
        { default: () => "Insight" },
      ),
  },
]);
</script>
