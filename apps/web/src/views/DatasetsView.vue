<template>
  <div>
    <template v-if="!orgStore.currentOrgId">
      <div style="padding: 48px; text-align: center;">
        <n-empty description="You are not a member of any organization. Contact an admin." />
      </div>
    </template>
    <template v-else>
    <n-space justify="space-between" align="center" style="margin-bottom: 16px">
      <n-h2 style="margin: 0">Datasets</n-h2>
      <n-space>
        <n-button @click="showImportFlow = true">
          Import Dataset
        </n-button>
        <n-button type="primary" @click="showPreviewFlow = true">
          Preview Dataset
        </n-button>
      </n-space>
    </n-space>

    <n-spin :show="isLoading">
      <n-data-table
        :columns="columns"
        :data="datasets ?? []"
        :row-props="rowProps"
        :bordered="false"
        style="cursor: pointer"
      />
    </n-spin>

    <PluginFlowModal
      v-model:show="showImportFlow"
      :plugins="importerPlugins"
      kind="import"
      title="Import Dataset"
      @complete="handleImportComplete"
    />

    <PluginFlowModal
      v-model:show="showPreviewFlow"
      :plugins="previewLauncherPlugins"
      kind="preview"
      title="Preview Dataset"
      @complete="handlePreviewComplete"
    />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, h, computed } from "vue";
import { useRouter } from "vue-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/vue-query";
import { useMessage } from "naive-ui";
import { NButton, NTag } from "naive-ui";
import { api } from "../api";
import type { Dataset } from "../types";
import { useOrgStore } from "../stores/org";
import { useAuthStore } from "../stores/auth";
import { pluginRegistry } from "../core/registry";
import PluginFlowModal from "../components/PluginFlowModal.vue";
import type { PluginCard } from "../components/PluginTypeSelector.vue";

const router = useRouter();
const message = useMessage();
const qc = useQueryClient();
const orgStore = useOrgStore();
const authStore = useAuthStore();

const showImportFlow = ref(false);
const showPreviewFlow = ref(false);

const importerPlugins = computed<PluginCard[]>(() =>
  pluginRegistry.getImporters("dataset").map((p) => ({
    id: p.id,
    label: p.label,
    description: p.description,
    icon: p.icon,
    component: p.component,
  }))
);

const previewLauncherPlugins = computed<PluginCard[]>(() =>
  pluginRegistry.getPreviewLaunchers("dataset-list").map((p) => ({
    id: p.id,
    label: p.label,
    description: p.description,
    icon: p.icon,
    component: p.component,
  }))
);

function handleImportComplete() {
  showImportFlow.value = false;
  qc.invalidateQueries({ queryKey: ["datasets", orgStore.currentOrgId] });
}

function handlePreviewComplete(result: unknown) {
  showPreviewFlow.value = false;
  const r = result as { sessionId?: string };
  if (r?.sessionId) {
    router.push({ name: "preview-classify", params: { sessionId: r.sessionId } });
  }
}

const { data: datasets, isLoading } = useQuery({
  queryKey: computed(() => ["datasets", orgStore.currentOrgId]),
  queryFn: api.listDatasets,
  enabled: computed(() => !!orgStore.currentOrgId),
});

const toggleDatasetPublicMut = useMutation({
  mutationFn: ({ id, isPublic }: { id: string; isPublic: boolean }) =>
    api.toggleDatasetPublic(id, isPublic),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["datasets", orgStore.currentOrgId] });
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to update visibility");
  },
});

const deleteDataset = useMutation({
  mutationFn: (datasetId: string) => api.deleteDataset(datasetId),
  onSuccess: () => {
    message.success("Dataset deleted");
    qc.invalidateQueries({ queryKey: ["datasets", orgStore.currentOrgId] });
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to delete dataset");
  },
});

function onDeleteDataset(row: Dataset) {
  if (!window.confirm(`Delete dataset '${row.name}'? This removes its local jobs, samples, models, and Label Studio project.`)) {
    return;
  }
  deleteDataset.mutate(row.id);
}

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
      if (row.is_public && row.org_id !== orgStore.currentOrgId) {
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
      h(NTag, { type: "info", size: "small" }, { default: () => row.task_spec.task_type }),
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
      const nodes = [
        h(
          NButton,
          {
            size: "small",
            onClick: (e: MouseEvent) => {
              e.stopPropagation();
              router.push(`/datasets/${row.id}`);
            },
          },
          { default: () => "View" }
        ),
      ];
      if (authStore.user?.is_superadmin === true && row.org_id === orgStore.currentOrgId) {
        nodes.push(
          h(
            NButton,
            {
              size: "small",
              style: "margin-left: 6px",
              onClick: (e: MouseEvent) => {
                e.stopPropagation();
                toggleDatasetPublicMut.mutate({ id: row.id, isPublic: !row.is_public });
              },
            },
            { default: () => (row.is_public ? "Make Private" : "Make Public") }
          )
        );
        nodes.push(
          h(
            NButton,
            {
              size: "small",
              type: "error",
              style: "margin-left: 6px",
              onClick: (e: MouseEvent) => {
                e.stopPropagation();
                onDeleteDataset(row);
              },
            },
            { default: () => "Delete" }
          )
        );
      }
      return h("span", {}, nodes);
    },
  },
];

function rowProps(row: Dataset) {
  return {
    onClick: () => {
      router.push(`/datasets/${row.id}`);
    },
  };
}
</script>