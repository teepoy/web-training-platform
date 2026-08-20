<template>
  <div data-testid="datasets-shim-sc">
    <n-data-table
      :columns="controlledColumns"
      :data="datasets"
      :row-key="(row: DatasetListItem) => row.id"
      :checked-row-keys="checkedRowKeys"
      :bordered="false"
      size="small"
      :pagination="pagination"
      :scroll-x="904"
      :row-props="rowProps"
      remote
      @update:checked-row-keys="handleCheckedRowKeysChange"
      @update:sorter="handleSorterChange"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, h } from "vue";
import type {
  DataTableColumns,
  DataTableRowKey,
  DataTableSortState,
  PaginationProps,
} from "naive-ui";
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
    sorter?: DataTableSortState | null;
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
  "update:sorter": [sorter: DataTableSortState | null];
}>();

function handleCheckedRowKeysChange(keys: DataTableRowKey[]) {
  emit("update:checked-row-keys", keys);
}

function handleSorterChange(sorter: DataTableSortState | DataTableSortState[] | null): void {
  emit("update:sorter", Array.isArray(sorter) ? (sorter[0] ?? null) : sorter);
}

function rowProps(row: DatasetListItem): Record<string, unknown> {
  return {
    style: { cursor: "pointer" },
    onClick: (event: MouseEvent) => {
      const target = event.target;
      if (
        target instanceof Element &&
        target.closest("button, a, input, [role='checkbox'], [data-stop-row-click]")
      ) {
        return;
      }
      emit("view", row.id);
    },
  };
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
    fixed: "left",
    disabled: (row) => row.created_by !== props.currentUserId,
  },
  {
    title: "Name",
    key: "name",
    width: 220,
    sorter: true,
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
    key: "creator",
    width: 160,
    sorter: true,
    render(row) {
      return h(NText, {}, { default: () => resolveCreator(row) });
    },
  },
  {
    title: "Create Time",
    key: "created_at",
    width: 180,
    sorter: true,
    render(row) {
      return h(NText, {}, { default: () => formatCreateTime(row.created_at) });
    },
  },
  {
    title: "Actions",
    key: "actions",
    width: 150,
    fixed: "right",
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

const controlledColumns = computed<DataTableColumns<DatasetListItem>>(() =>
  columns.value.map((column) => {
    if (!("key" in column) || !("sorter" in column) || !column.sorter) return column;
    return {
      ...column,
      sortOrder: props.sorter?.columnKey === column.key ? props.sorter.order : false,
    };
  }),
);
</script>
