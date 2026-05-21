<template>
  <n-space vertical size="large">
    <n-page-header title="Task Explorer" />
    <n-spin :show="isLoading">
      <n-data-table
        :columns="columns"
        :data="tasks ?? []"
        :bordered="true"
        :striped="true"
        :loading="isLoading"
      />
    </n-spin>
  </n-space>
</template>

<script setup lang="ts">
import { computed, h } from "vue";
import type { DataTableColumns } from "naive-ui";
import { NTag } from "naive-ui";
import { useTrackedTasksQuery } from "../../infrastructure/api";
import type { TaskTrackerSummary } from "../../infrastructure/api";

const { data: tasks, isLoading } = useTrackedTasksQuery();

const columns = computed<DataTableColumns<TaskTrackerSummary>>(() => [
  { title: "Task", key: "display_name", ellipsis: { tooltip: true } },
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
]);
</script>
