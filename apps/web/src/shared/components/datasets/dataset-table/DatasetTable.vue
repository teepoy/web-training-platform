<template>
  <n-data-table
    :columns="columns"
    :data="datasets"
    :row-props="rowProps"
    :bordered="false"
    style="cursor: pointer"
  />
</template>

<script setup lang="ts" generic="TDataset extends DatasetListItem">
import type { DataTableColumns } from "naive-ui";

import type { DatasetListItem } from "../../../datasets/types";

const props = defineProps<{
  datasets: TDataset[];
  columns: DataTableColumns<TDataset>;
  onRowClick: (row: TDataset) => void;
}>();

function rowProps(row: TDataset) {
  return {
    onClick: () => props.onRowClick(row),
  };
}
</script>
