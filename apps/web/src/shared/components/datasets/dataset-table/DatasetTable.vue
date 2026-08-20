<template>
  <n-data-table
    :columns="tableColumns"
    :data="datasets"
    :row-props="rowProps"
    :row-key="(row: TDataset) => row.id"
    :checked-row-keys="checkedRowKeys"
    :bordered="false"
    :pagination="pagination"
    :scroll-x="1080"
    remote
    style="cursor: pointer"
    @update:checked-row-keys="handleCheckedRowKeysChange"
    @update:sorter="handleSorterChange"
  />
</template>

<script setup lang="ts" generic="TDataset extends DatasetListItem">
import { computed } from "vue";
import type {
  DataTableColumns,
  DataTableRowKey,
  DataTableSortState,
  PaginationProps,
} from "naive-ui";

import type { DatasetListItem } from "../../../datasets/types";

const props = defineProps<{
  datasets: TDataset[];
  columns: DataTableColumns<TDataset>;
  onRowClick: (row: TDataset) => void;
  checkedRowKeys?: DataTableRowKey[];
  rowCheckable?: (row: TDataset) => boolean;
  onUpdateCheckedRowKeys?: (keys: DataTableRowKey[]) => void;
  pagination?: false | PaginationProps;
  sorter?: DataTableSortState | null;
  onUpdateSorter?: (sorter: DataTableSortState | null) => void;
}>();

const tableColumns = computed<DataTableColumns<TDataset>>(() => {
  const controlledColumns = props.columns.map((column) => {
    if (!("key" in column) || !("sorter" in column) || !column.sorter) return column;
    return {
      ...column,
      sortOrder: props.sorter?.columnKey === column.key ? props.sorter.order : false,
    };
  });
  if (!props.onUpdateCheckedRowKeys) return controlledColumns;
  return [
    {
      type: "selection",
      fixed: "left",
      disabled: (row: TDataset) => (props.rowCheckable ? !props.rowCheckable(row) : false),
    },
    ...controlledColumns,
  ];
});

function rowProps(row: TDataset) {
  return {
    onClick: (event: MouseEvent) => {
      const target = event.target;
      if (
        target instanceof Element &&
        target.closest("button, a, input, [role='checkbox'], [data-stop-row-click]")
      ) {
        return;
      }
      props.onRowClick(row);
    },
  };
}

function handleCheckedRowKeysChange(keys: DataTableRowKey[]): void {
  props.onUpdateCheckedRowKeys?.(keys);
}

function handleSorterChange(sorter: DataTableSortState | DataTableSortState[] | null): void {
  props.onUpdateSorter?.(Array.isArray(sorter) ? (sorter[0] ?? null) : sorter);
}
</script>
