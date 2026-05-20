<template>
  <div>
      <DatasetPageShell v-bind="surface.pageShellProps.value">
        <component
          :is="activeShim"
          :datasets="surface.datasets.value"
          :current-org-id="orgStore.currentOrgId"
          :is-superadmin="authStore.user?.is_superadmin ?? false"
          :importer-flows="surface.toolbarProps.value.importerFlows"
          :preview-launcher-flows="surface.toolbarProps.value.previewLauncherFlows"
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
import { DatasetPageShell, useDatasetListSurface, type FlowCard } from "@platform/web-ui";
import { toggleDatasetPublic } from "@platform/web-ui/api/datasets";
import { listDatasets, deleteDataset } from "@platform/web-ui/api/datasets";
import type { Dataset, User } from "../types";
import { useOrgStore } from "../stores/org";
import { useAuthStore } from "../stores/auth";
import ManualImporter from "../features/dataset-detail/components/ManualImporter.vue";
import ManualDatasetImporter from "../features/dataset-detail/components/ManualDatasetImporter.vue";
import ParquetImporter from "../features/dataset-detail/components/ParquetImporter.vue";
import UpstreamPreviewLauncher from "../features/preview/components/UpstreamPreviewLauncher.vue";
import { resolveDatasetShim, resolveDatasetTaskType } from "./datasets/registry";
import { getActiveDatasetTaskType, getActiveDatasetType } from "./datasets/selection";

const router = useRouter();
const message = useMessage();
const qc = useQueryClient();
const orgStore = useOrgStore();
const authStore = useAuthStore();

const { data: datasets, isLoading, error } = useQuery({
  queryKey: computed(() => ["datasets", orgStore.currentOrgId]),
  queryFn: listDatasets,
  enabled: computed(() => !!orgStore.currentOrgId),
});

const toggleDatasetPublicMut = useMutation({
  mutationFn: ({ id, isPublic }: { id: string; isPublic: boolean }) =>
    toggleDatasetPublic(id, isPublic),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["datasets", orgStore.currentOrgId] });
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to update visibility");
  },
});

const deleteDatasetMut = useMutation({
  mutationFn: (datasetId: string) => deleteDataset(datasetId),
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

const importerFlows = computed<FlowCard[]>(() => [
  {
    id: "import-manual",
    label: "Manual Sample Entry",
    description: "Create one sample at a time with URI, metadata, or uploaded image.",
    icon: "✏️",
    component: ManualImporter,
  },
  {
    id: "import-dataset-manual",
    label: "Import from JSON",
    description: "Create a dataset by uploading a JSON file of sample items.",
    icon: "📁",
    component: ManualDatasetImporter,
  },
  {
    id: "import-parquet",
    label: "Import from Parquet",
    description: "Import samples from a HuggingFace-compatible Parquet file (image struct with bytes/path columns).",
    icon: "📦",
    component: ParquetImporter,
  },
]);
const previewLauncherFlows = computed<FlowCard[]>(() => [
  {
    id: "preview-upstream",
    label: "Upstream Collection",
    description: "Browse a remote collection without importing it first.",
    icon: "🔍",
    component: UpstreamPreviewLauncher,
  },
]);

const surface = useDatasetListSurface<Dataset, User>({
  datasets,
  isLoading,
  error,
  currentOrgId: computed(() => orgStore.currentOrgId),
  user: computed(() => authStore.user),
  importerFlows,
  previewLauncherFlows,
  resolveTaskType: resolveDatasetTaskType,
  onViewDataset: handleViewDataset,
  onTogglePublic: handleTogglePublic,
  onDeleteDataset: handleDeleteDataset,
});

const activeTaskType = computed(() => getActiveDatasetTaskType(datasets.value));
const activeDatasetType = computed(() => getActiveDatasetType(datasets.value));

const activeShim = computed(() => resolveDatasetShim(activeDatasetType.value));
</script>
