<template>
  <div data-testid="datasets-shim-detection">
    <DatasetToolbar
      title="Object Detection Datasets"
      :importer-flows="importerPlugins"
      :preview-launcher-flows="previewLauncherPlugins"
      @import-complete="emit('import-complete')"
      @preview-complete="(res) => emit('preview-complete', res)"
    />

    <n-alert type="info" style="margin-bottom: 16px">
      Object Detection workspace — samples contain bounding box annotations.
    </n-alert>

    <DatasetTable
      :datasets="datasets"
      :columns="columns"
      :on-row-click="(row) => emit('view', row.id)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { NAlert } from "naive-ui";
import { DatasetTable, DatasetToolbar, type FlowCard } from "@/shared";
import { buildDatasetColumns } from "@/features/datasets/application/surface";
import type { Dataset } from "@/features/datasets/domain/models";
import { resolveDatasetTaskType } from "../registry";

const props = defineProps<{
  datasets: Dataset[];
  currentOrgId: string | null;
  isSuperadmin: boolean;
  importerPlugins: FlowCard[];
  previewLauncherPlugins: FlowCard[];
}>();

const emit = defineEmits<{
  "import-complete": [];
  "preview-complete": [result: unknown];
  "view": [id: string];
  "toggle-public": [payload: { id: string; isPublic: boolean }];
  "delete": [row: Dataset];
}>();

const columns = computed(() =>
  buildDatasetColumns<Dataset>({
    currentOrgId: props.currentOrgId,
    isSuperadmin: props.isSuperadmin,
    taskTagType: "error",
    resolveTaskType: resolveDatasetTaskType,
    onViewDataset: (id: string) => emit("view", id),
    onTogglePublic: (payload: { id: string; isPublic: boolean }) => emit("toggle-public", payload),
    onDeleteDataset: (row: Dataset) => emit("delete", row),
  }),
);
</script>
