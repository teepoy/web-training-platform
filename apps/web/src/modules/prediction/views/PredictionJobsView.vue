<template>
  <n-space vertical size="large">
    <n-page-header title="Prediction Jobs" />
    <n-spin :show="isLoading">
      <n-data-table
        :columns="columns"
        :data="jobs ?? []"
        :bordered="true"
        :striped="true"
        :loading="isLoading"
      />
    </n-spin>
  </n-space>
</template>

<script setup lang="ts">
import { computed, h } from "vue";
import { useQuery } from "@tanstack/vue-query";
import type { DataTableColumns } from "naive-ui";
import { NTag } from "naive-ui";
import { listPredictionJobs } from "../api";
import type { PredictionJob } from "../types";

const { data: jobs, isLoading } = useQuery({
  queryKey: ["prediction-jobs"],
  queryFn: listPredictionJobs,
  refetchInterval: 5000,
});

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
    render: (row) => row.dataset_id.slice(0, 8) + "…",
  },
  {
    title: "Model ID",
    key: "model_id",
    ellipsis: { tooltip: true },
    render: (row) => row.model_id.slice(0, 8) + "…",
  },
  {
    title: "Target",
    key: "target",
    width: 160,
  },
  {
    title: "Created At",
    key: "created_at",
    width: 180,
    render: (row) => new Date(row.created_at).toLocaleString(),
  },
]);
</script>
