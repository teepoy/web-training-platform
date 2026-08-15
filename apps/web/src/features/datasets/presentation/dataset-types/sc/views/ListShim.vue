<template>
  <div data-testid="datasets-shim-sc">
    <n-data-table
      :columns="columns"
      :data="datasets"
      :row-key="(row: DatasetListItem) => row.id"
      :checked-row-keys="checkedRowKeys"
      :bordered="false"
      size="small"
      :pagination="pagination"
      remote
      @update:checked-row-keys="handleCheckedRowKeysChange"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, h } from "vue";
import type { DataTableColumns, DataTableRowKey, PaginationProps } from "naive-ui";
import { NButton, NDataTable, NTag, NText, NSpace } from "naive-ui";
import type { DatasetListItem } from "@/shared/datasets/types";

const props = withDefaults(
  defineProps<{
    datasets: DatasetListItem[];
    currentOrgId: string | null;
    currentUserId?: string | null;
    isSuperadmin: boolean;
    checkedRowKeys?: DataTableRowKey[];
    pagination?: false | PaginationProps;
  }>(),
  {
    currentUserId: null,
    checkedRowKeys: () => [],
  },
);

const emit = defineEmits<{
  view: [id: string];
  "toggle-public": [payload: { id: string; isPublic: boolean }];
  rename: [row: DatasetListItem];
  delete: [row: DatasetListItem];
  "update:checked-row-keys": [keys: DataTableRowKey[]];
}>();

function handleCheckedRowKeysChange(keys: DataTableRowKey[]) {
  emit("update:checked-row-keys", keys);
}

function resolveCreator(row: DatasetListItem): string {
  return row.creator_name?.trim() || row.created_by?.trim() || "system";
}

function formatCreateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

const columns = computed<DataTableColumns<DatasetListItem>>(() => [
  {
    type: "selection",
    disabled: (row) => row.created_by !== props.currentUserId,
  },
  {
    title: "Name",
    key: "name",
    width: 220,
    sorter: "default",
    render(row) {
      return h(NText, { style: "font-weight: 500" }, { default: () => row.name });
    },
  },
  {
    title: "Task Type",
    key: "task_type",
    width: 150,
    render() {
      return h(NTag, { type: "info", size: "small", bordered: false }, { default: () => "Patch" });
    },
  },
  {
    title: "Creator",
    key: "created_by",
    width: 160,
    sorter: "default",
    render(row) {
      return h(NText, {}, { default: () => resolveCreator(row) });
    },
  },
  {
    title: "Create Time",
    key: "created_at",
    width: 180,
    sorter: (left, right) =>
      new Date(left.created_at).getTime() - new Date(right.created_at).getTime(),
    render(row) {
      return h(NText, {}, { default: () => formatCreateTime(row.created_at) });
    },
  },
  {
    title: "Actions",
    key: "actions",
    width: 150,
    render(row) {
      return h(
        NSpace,
        { size: 6, wrap: false },
        {
          default: () => [
            h(
              NButton,
              {
                size: "small",
                quaternary: true,
                onClick: () => emit("view", row.id),
              },
              { default: () => "View" },
            ),
            h(
              NButton,
              {
                size: "small",
                quaternary: true,
                disabled: row.created_by !== props.currentUserId,
                onClick: () => emit("rename", row),
              },
              { default: () => "Rename" },
            ),
            row.created_by === props.currentUserId
              ? h(
                  NButton,
                  {
                    size: "small",
                    quaternary: true,
                    type: "error",
                    onClick: () => emit("delete", row),
                  },
                  { default: () => "Delete" },
                )
              : null,
          ],
        },
      );
    },
  },
]);
</script>
