<template>
  <div data-testid="datasets-shim-classification">
    <DatasetTable
      :datasets="datasets"
      :columns="columns"
      :on-row-click="(row) => emit('view', row.id)"
      :checked-row-keys="checkedRowKeys"
      :row-checkable="(row) => row.created_by === currentUserId"
      :on-update-checked-row-keys="(keys) => emit('update:checked-row-keys', keys)"
      :pagination="pagination"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { DataTableRowKey } from "naive-ui";
import { DatasetTable } from "@/shared";
import { buildDatasetColumns } from "@/features/datasets/application/surface";
import { resolveDatasetTaskType } from "@/features/datasets/presentation/pages/registry";
import type { DatasetListItem } from "@/shared/datasets/types";

const props = defineProps<{
  datasets: DatasetListItem[];
  currentOrgId: string | null;
  currentUserId?: string | null;
  isSuperadmin: boolean;
  checkedRowKeys?: DataTableRowKey[];
  pagination?: false | import("naive-ui").PaginationProps;
}>();

const emit = defineEmits<{
  view: [id: string];
  "toggle-public": [payload: { id: string; isPublic: boolean }];
  rename: [row: DatasetListItem];
  delete: [row: DatasetListItem];
  "update:checked-row-keys": [keys: DataTableRowKey[]];
}>();

const columns = computed(() =>
  buildDatasetColumns<DatasetListItem>({
    currentOrgId: props.currentOrgId,
    isSuperadmin: props.isSuperadmin,
    currentUserId: props.currentUserId,
    resolveTaskType: resolveDatasetTaskType,
    onViewDataset: (id: string) => emit("view", id),
    onTogglePublic: (payload: { id: string; isPublic: boolean }) => emit("toggle-public", payload),
    onRenameDataset: (id: string, name: string) => emit("rename", { id, name } as DatasetListItem),
    onDeleteDataset: (row: DatasetListItem) => emit("delete", row),
  }),
);
</script>
