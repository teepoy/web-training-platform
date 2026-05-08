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
import { h } from "vue";
import { NTag } from "naive-ui";
import type { Dataset } from "../../../types";
import DatasetToolbar from "../../../components/datasets/DatasetToolbar.vue";
import DatasetTable from "../../../components/datasets/DatasetTable.vue";
import DatasetRowActions from "../../../components/datasets/DatasetRowActions.vue";
import type { PluginCard } from "../../../components/PluginTypeSelector.vue";
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

const columns = [
  {
    title: "Name",
    key: "name",
    render: (row: Dataset) => {
      const nodes = [h("span", { style: "font-weight: 500" }, row.name)];
      if (row.is_public) {
        nodes.push(
          h(NTag, { type: "info", size: "small", style: "margin-left: 6px" }, { default: () => "Public" })
        );
      }
      if (row.is_public && row.org_id !== props.currentOrgId) {
        nodes.push(
          h("span", { style: "margin-left: 4px; font-size: 12px; color: #aaa" }, `(${row.org_name ?? "Other Org"})`)
        );
      }
      return h("span", {}, nodes);
    },
  },
  {
    title: "Dataset Type",
    key: "dataset_type",
    render: (row: Dataset) =>
      h(NTag, { type: "default", size: "small" }, { default: () => row.dataset_type }),
  },
  {
    title: "Task Type",
    key: "task_type",
    render: (row: Dataset) =>
      h(NTag, { type: "info", size: "small" }, { default: () => resolveDatasetTaskType(row.task_spec?.task_type) }),
  },
  {
    title: "Created At",
    key: "created_at",
    render: (row: Dataset) =>
      h("span", {}, new Date(row.created_at).toLocaleString()),
  },
  {
    title: "Actions",
    key: "actions",
    render: (row: Dataset) => {
      return h(DatasetRowActions, {
        row,
        isSuperadmin: props.isSuperadmin,
        isOwnOrg: row.org_id === props.currentOrgId,
        onView: (id: string) => emit("view", id),
        "onToggle-public": (payload: { id: string; isPublic: boolean }) => emit("toggle-public", payload),
        onDelete: (r: Dataset) => emit("delete", r),
      });
    },
  },
];
</script>
