<template>
  <n-data-table
    :columns="columns"
    :data="datasets"
    :row-props="rowProps"
    :bordered="false"
    :pagination="pagination"
    remote
    style="cursor: pointer"
  />
</template>

<script setup lang="ts" generic="TDataset extends DatasetListItem">
import type { DataTableColumns, PaginationProps } from "naive-ui";

import type { DatasetListItem } from "../../../datasets/types";

const props = defineProps<{
  datasets: TDataset[];
  columns: DataTableColumns<TDataset>;
  onRowClick: (row: TDataset) => void;
  pagination?: false | PaginationProps;
}>();

function rowProps(row: TDataset) {
  return {
    onClick: () => props.onRowClick(row),
  };
}
</script>
