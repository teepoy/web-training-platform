<template>
  <div>
    <DatasetPageShell v-bind="adapter.pageShellProps.value">
      <component
        :is="activeShim"
        :datasets="adapter.datasets.value"
        :current-org-id="orgStore.currentOrgId"
        :is-superadmin="authStore.user?.is_superadmin ?? false"
        :importer-plugins="adapter.toolbarProps.value.importerPlugins"
        :preview-launcher-plugins="adapter.toolbarProps.value.previewLauncherPlugins"
        @import-complete="handleImportComplete"
        @preview-complete="handlePreviewComplete"
        @view="handleViewDataset"
        @toggle-public="handleTogglePublic"
        @delete="handleDeleteDataset"
      />
    </DatasetPageShell>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRouter } from "vue-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/vue-query";
import { useMessage } from "naive-ui";
import { api } from "../api";
import type { Dataset } from "../types";
import { useOrgStore } from "../stores/org";
import { useAuthStore } from "../stores/auth";
import DatasetPageShell from "../components/datasets/DatasetPageShell.vue";
import { resolveDatasetShim } from "./datasets/registry";
import { useDatasetsAdapter } from "../composables/useDatasetsAdapter";
import { getActiveDatasetTaskType } from "./datasets/selection";

const router = useRouter();
const message = useMessage();
const qc = useQueryClient();
const orgStore = useOrgStore();
const authStore = useAuthStore();

const { data: datasets, isLoading, error } = useQuery({
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

const deleteDatasetMut = useMutation({
  mutationFn: (datasetId: string) => api.deleteDataset(datasetId),
  onSuccess: () => {
    message.success("Dataset deleted");
    qc.invalidateQueries({ queryKey: ["datasets", orgStore.currentOrgId] });
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to delete dataset");
  },
});

function handleImportComplete() {
  qc.invalidateQueries({ queryKey: ["datasets", orgStore.currentOrgId] });
}

function handlePreviewComplete(result: unknown) {
  const r = result as { sessionId?: string };
  if (r?.sessionId) {
    router.push({ name: "preview-classify", params: { sessionId: r.sessionId } });
  }
}

function handleViewDataset(datasetId: string) {
  router.push(`/datasets/${datasetId}`);
}

function handleTogglePublic(payload: { id: string; isPublic: boolean }) {
  toggleDatasetPublicMut.mutate(payload);
}

function handleDeleteDataset(row: Dataset) {
  if (!window.confirm(`Delete dataset '${row.name}'? This removes its local jobs, samples, models, and Label Studio project.`)) {
    return;
  }
  deleteDatasetMut.mutate(row.id);
}

const adapter = useDatasetsAdapter({
  datasets,
  isLoading,
  error,
  currentOrgId: computed(() => orgStore.currentOrgId),
  user: computed(() => authStore.user),
  onViewDataset: handleViewDataset,
  onTogglePublic: handleTogglePublic,
  onDeleteDataset: handleDeleteDataset,
  onImportComplete: handleImportComplete,
  onPreviewComplete: handlePreviewComplete,
});

const activeTaskType = computed(() => getActiveDatasetTaskType(datasets.value));

const activeShim = computed(() => resolveDatasetShim(activeTaskType.value));
</script>
