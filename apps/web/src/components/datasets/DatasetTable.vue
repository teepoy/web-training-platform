<template>
  <n-data-table
    :columns="columns"
    :data="datasets"
    :row-props="rowProps"
    :bordered="false"
    style="cursor: pointer"
  />
</template>

<script setup lang="ts">
import type { DataTableColumns } from "naive-ui";
import type { Dataset } from "../../types";

const props = defineProps<{
  datasets: Dataset[];
  columns: DataTableColumns<Dataset>;
  onRowClick: (row: Dataset) => void;
}>();

function rowProps(row: Dataset) {
  return {
    onClick: () => props.onRowClick(row),
  };
}
</script>
