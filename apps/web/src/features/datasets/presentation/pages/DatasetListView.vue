<template>
  <div>
      <DatasetPageShell v-bind="surface.pageShellProps.value">
        <component
          :is="activeShim"
          :datasets="surface.datasets.value"
          :current-org-id="orgStore.currentOrgId"
          :is-superadmin="authStore.user?.is_superadmin ?? false"
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
import { DatasetPageShell } from "@/shared";
import { deleteDataset, listDatasets, toggleDatasetPublic } from "@/shared/api/datasets";
import { useOrgStore } from '@/features/auth/application/org';
import { useAuthStore } from '@/features/auth/application/store';
import { useDatasetListSurface } from "@/features/datasets/application/surface";
import { resolveDatasetShim } from "./schema-registry";
import { resolveDatasetTaskType } from "./registry";
import { getActiveDatasetTaskType, getActiveDatasetType, getActiveViewTypes } from "./selection";
import type { UserResponse as User } from "@/generated/orval/models";
import type { DatasetListItem } from "@/shared/datasets/types";

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

function handleViewDataset(datasetId: string) {
  router.push(`/datasets/${datasetId}`);
}

function handleTogglePublic(payload: { id: string; isPublic: boolean }) {
  toggleDatasetPublicMut.mutate(payload);
}

function handleDeleteDataset(row: DatasetListItem) {
  if (!window.confirm(`Delete dataset '${row.name}'? This removes its local jobs, samples, models, and Label Studio project.`)) {
    return;
  }
  deleteDatasetMut.mutate(row.id!);
}

const surface = useDatasetListSurface<DatasetListItem, User>({
  datasets: computed(() => (datasets.value ?? []) as DatasetListItem[]),
  isLoading,
  error,
  currentOrgId: computed(() => orgStore.currentOrgId),
  user: computed(() => authStore.user),
  resolveTaskType: resolveDatasetTaskType,
  onViewDataset: handleViewDataset,
  onTogglePublic: handleTogglePublic,
  onDeleteDataset: handleDeleteDataset,
});

const activeTaskType = computed(() => getActiveDatasetTaskType(datasets.value));
const activeDatasetType = computed(() => getActiveDatasetType(datasets.value));
const activeViewTypes = computed(() => getActiveViewTypes(datasets.value));

const activeShim = computed(() => resolveDatasetShim(activeDatasetType.value, activeViewTypes.value));
</script>
