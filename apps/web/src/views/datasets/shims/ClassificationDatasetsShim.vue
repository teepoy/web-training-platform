<template>
  <div data-testid="datasets-shim-classification">
    <DatasetToolbar
      :importer-plugins="importerPlugins"
      :preview-launcher-plugins="previewLauncherPlugins"
      @import-complete="emit('import-complete')"
      @preview-complete="(res) => emit('preview-complete', res)"
    />

    <DatasetTable
      :datasets="datasets"
      :columns="columns"
      :on-row-click="(row) => emit('view', row.id)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { buildDatasetColumns, DatasetTable, DatasetToolbar, type PluginCard } from "@platform/web-ui";
import type { Dataset } from "../../../types";
import { resolveDatasetTaskType } from "../registry";

const props = defineProps<{
  datasets: Dataset[];
  currentOrgId: string | null;
  isSuperadmin: boolean;
  importerPlugins: PluginCard[];
  previewLauncherPlugins: PluginCard[];
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
    resolveTaskType: resolveDatasetTaskType,
    onViewDataset: (id) => emit("view", id),
    onTogglePublic: (payload) => emit("toggle-public", payload),
    onDeleteDataset: (row) => emit("delete", row),
  }),
);
</script>
