<template>
  <n-data-table
    :columns="tableColumns"
    :data="datasets"
    :row-props="rowProps"
    :row-key="(row: TDataset) => row.id"
    :checked-row-keys="checkedRowKeys"
    :bordered="false"
    :pagination="pagination"
    remote
    style="cursor: pointer"
    @update:checked-row-keys="handleCheckedRowKeysChange"
  />
</template>

<script setup lang="ts" generic="TDataset extends DatasetListItem">
import { computed } from "vue";
import type { DataTableColumns, DataTableRowKey, PaginationProps } from "naive-ui";

import type { DatasetListItem } from "../../../datasets/types";

const props = defineProps<{
  datasets: TDataset[];
  columns: DataTableColumns<TDataset>;
  onRowClick: (row: TDataset) => void;
  checkedRowKeys?: DataTableRowKey[];
  rowCheckable?: (row: TDataset) => boolean;
  onUpdateCheckedRowKeys?: (keys: DataTableRowKey[]) => void;
  pagination?: false | PaginationProps;
}>();

const tableColumns = computed<DataTableColumns<TDataset>>(() => {
  if (!props.onUpdateCheckedRowKeys) return props.columns;
  return [
    {
      type: "selection",
      disabled: (row: TDataset) => (props.rowCheckable ? !props.rowCheckable(row) : false),
    },
    ...props.columns,
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
</script>
