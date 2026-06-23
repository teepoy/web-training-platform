<template>
  <div data-testid="datasets-shim-sc">
    <DatasetToolbar title="Patch Datasets" />

    <n-data-table
      :columns="columns"
      :data="datasets"
      :row-key="(row: DatasetListItem) => row.id"
      :bordered="false"
      size="small"
      @update:checked-row-keys="handleCheckedRowKeysChange"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, h } from "vue";
import type { DataTableColumns } from "naive-ui";
import { NButton, NDataTable, NTag, NText } from "naive-ui";
import { DatasetToolbar } from "@/shared";
import type { DatasetListItem } from "@/shared/datasets/types";

const props = defineProps<{
  datasets: DatasetListItem[];
  currentOrgId: string | null;
  isSuperadmin: boolean;
}>();

const emit = defineEmits<{
  view: [id: string];
  "toggle-public": [payload: { id: string; isPublic: boolean }];
  delete: [row: DatasetListItem];
}>();

function handleCheckedRowKeysChange(_keys: (string | number)[]) {
  // Reserved for batch operations
}

function toDisplayCount(value: unknown): string | null {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "string" && value.trim() !== "") return value;
  return null;
}

function resolveSampleCount(row: DatasetListItem): string {
  const meta = row.dataset_meta ?? {};
  return (
    toDisplayCount(meta.sample_count) ??
    toDisplayCount(meta.total_samples) ??
    toDisplayCount(meta.samples_count) ??
    toDisplayCount(meta.total_rows) ??
    "0"
  );
}

function formatCreateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

const columns = computed<DataTableColumns<DatasetListItem>>(
  () => [
    {
      title: "Name",
      key: "name",
      width: 220,
      render(row) {
        return h(NText, { style: "font-weight: 500" }, { default: () => row.name });
      },
    },
    {
      title: "Task Type",
      key: "task_type",
      width: 150,
      render() {
        return h(
          NTag,
          { type: "info", size: "small", bordered: false },
          { default: () => "Patch" },
        );
      },
    },
    {
      title: "Samples",
      key: "sample_count",
      width: 100,
      render(row) {
        return h(NText, {}, { default: () => resolveSampleCount(row) });
      },
    },
    {
      title: "Create Time",
      key: "created_at",
      width: 180,
      render(row) {
        return h(NText, {}, { default: () => formatCreateTime(row.created_at) });
      },
    },
    {
      title: "Actions",
      key: "actions",
      width: 100,
      render(row) {
        return h(
          NButton,
          {
            size: "small",
            quaternary: true,
            onClick: () => emit("view", row.id),
          },
          { default: () => "View" },
        );
      },
    },
  ],
);
</script>
