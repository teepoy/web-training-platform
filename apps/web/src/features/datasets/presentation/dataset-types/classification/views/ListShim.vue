<template>
  <div data-testid="datasets-shim-classification">
    <DatasetToolbar />

    <DatasetTable
      :datasets="datasets"
      :columns="columns"
      :on-row-click="(row) => emit('view', row.id)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { DatasetTable, DatasetToolbar } from "@/shared";
import { buildDatasetColumns } from "@/features/datasets/application/surface";
import { resolveDatasetTaskType } from "@/features/datasets/presentation/pages/registry";
import type { DatasetListItem } from "@/shared/datasets/types";

const props = defineProps<{
  datasets: DatasetListItem[];
  currentOrgId: string | null;
  isSuperadmin: boolean;
}>();

const emit = defineEmits<{
  "view": [id: string];
  "toggle-public": [payload: { id: string; isPublic: boolean }];
  "delete": [row: DatasetListItem];
}>();

const columns = computed(() =>
  buildDatasetColumns<DatasetListItem>({
    currentOrgId: props.currentOrgId,
    isSuperadmin: props.isSuperadmin,
    resolveTaskType: resolveDatasetTaskType,
    onViewDataset: (id: string) => emit("view", id),
    onTogglePublic: (payload: { id: string; isPublic: boolean }) => emit("toggle-public", payload),
    onDeleteDataset: (row: DatasetListItem) => emit("delete", row),
  }),
);
</script>
