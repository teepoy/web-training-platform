<template>
  <div>
    <DatasetPageShell v-bind="surface.pageShellProps.value">
      <DatasetToolbar :title="activeDatasetType === 'image_sc' ? 'Patch Datasets' : 'Datasets'" />

      <div class="dataset-list-filters">
        <n-input
          v-model:value="keyword"
          size="small"
          clearable
          placeholder="Search datasets"
          class="dataset-list-search"
        />
        <n-select
          v-model:value="creatorFilter"
          size="small"
          clearable
          filterable
          placeholder="Creator"
          :options="creatorOptions"
          class="dataset-list-creator"
        />
      </div>

      <component
        :is="activeShim"
        :datasets="surface.datasets.value"
        :current-org-id="orgStore.currentOrgId"
        :current-user-id="authStore.user?.id ?? null"
        :is-superadmin="authStore.user?.is_superadmin ?? false"
        :pagination="pagination"
        @view="handleViewDataset"
        @toggle-public="handleTogglePublic"
        @delete="handleDeleteDataset"
        @rename="handleRenameDataset"
      />
    </DatasetPageShell>

    <n-modal
      v-model:show="renameVisible"
      preset="dialog"
      title="Rename Dataset"
      positive-text="Save"
      negative-text="Cancel"
      :loading="renameMutation.isPending.value"
      @positive-click="submitRename"
      @negative-click="renameVisible = false"
    >
      <n-input
        v-model:value="renameName"
        placeholder="Enter new name"
        maxlength="255"
        show-count
        @keyup.enter="submitRename"
      />
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useQueryClient } from "@tanstack/vue-query";
import { refDebounced } from "@vueuse/core";
import { useMessage, NModal, NInput, NSelect, type PaginationProps } from "naive-ui";
import { DatasetPageShell, DatasetToolbar } from "@/shared";
import {
  getListDatasetsApiV1DatasetsGetQueryKey,
  useDeleteDatasetApiV1DatasetsDatasetIdDelete,
  useListDatasetsApiV1DatasetsGet,
  useListDatasetCreatorsApiV1DatasetsCreatorsGet,
  useSetDatasetPublicApiV1DatasetsDatasetIdPublicPatch,
  useUpdateDatasetApiV1DatasetsDatasetIdPatch,
} from "@/generated/orval/endpoints/api";
import { orgScopedQueryKey, toUserMessage } from "@/shared/api";
import { useOrgStore } from "@/features/auth/application/org";
import { useAuthStore } from "@/features/auth/application/store";
import { useDatasetListSurface } from "@/features/datasets/application/surface";
import { resolveDatasetShim } from "./schema-registry";
import { resolveDatasetTaskType } from "./registry";
import { getActiveDatasetType, getActiveViewTypes } from "./selection";
import type { UserResponse as User } from "@/generated/orval/models";
import type { DatasetListItem } from "@/shared/datasets/types";

const router = useRouter();
const message = useMessage();
const qc = useQueryClient();
const orgStore = useOrgStore();
const authStore = useAuthStore();
const keyword = ref("");
const debouncedKeyword = refDebounced(keyword, 250);
const creatorFilter = ref<string | null>(null);

const pagination = reactive<PaginationProps>({
  page: 1,
  pageSize: 20,
  itemCount: 0,
  showSizePicker: true,
  pageSizes: [10, 20, 50, 100],
  onUpdatePage: (page: number) => {
    pagination.page = page;
  },
  onUpdatePageSize: (pageSize: number) => {
    pagination.pageSize = pageSize;
    pagination.page = 1;
  },
});

const datasetListParams = computed(() => ({
  limit: pagination.pageSize ?? 20,
  offset: ((pagination.page ?? 1) - 1) * (pagination.pageSize ?? 20),
  q: debouncedKeyword.value.trim() || undefined,
  creator_id: creatorFilter.value ?? undefined,
}));
const datasetListQueryKey = computed(() =>
  orgScopedQueryKey(
    orgStore.currentOrgId,
    getListDatasetsApiV1DatasetsGetQueryKey(datasetListParams.value),
  ),
);
const datasetListQueryPrefix = computed(() =>
  orgScopedQueryKey(orgStore.currentOrgId, ["api", "v1", "datasets"]),
);

const {
  data: datasetPage,
  isLoading,
  error,
} = useListDatasetsApiV1DatasetsGet(datasetListParams, {
  query: {
    queryKey: datasetListQueryKey,
    enabled: computed(() => !!orgStore.currentOrgId),
  },
});

const datasets = computed(() => datasetPage.value?.items ?? []);

const { data: datasetCreators } = useListDatasetCreatorsApiV1DatasetsCreatorsGet({
  query: {
    queryKey: computed(() => orgScopedQueryKey(orgStore.currentOrgId, ["datasets", "creators"])),
    enabled: computed(() => !!orgStore.currentOrgId),
  },
});
const creatorOptions = computed(() =>
  (datasetCreators.value ?? []).map((creator) => ({
    label: creator.name,
    value: creator.id,
  })),
);

watch([keyword, creatorFilter], () => {
  pagination.page = 1;
});

watch(
  () => datasetPage.value?.total ?? 0,
  (total) => {
    pagination.itemCount = total;
  },
  { immediate: true },
);

const toggleDatasetPublicMut = useSetDatasetPublicApiV1DatasetsDatasetIdPublicPatch({
  mutation: {
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: datasetListQueryPrefix.value });
    },
    onError: (error) => {
      message.error(toUserMessage(error, "Failed to update visibility"));
    },
  },
});

const deleteDatasetMut = useDeleteDatasetApiV1DatasetsDatasetIdDelete({
  mutation: {
    onSuccess: () => {
      message.success("Dataset deleted");
      qc.invalidateQueries({ queryKey: datasetListQueryPrefix.value });
    },
    onError: (error) => {
      message.error(toUserMessage(error, "Failed to delete dataset"));
    },
  },
});

const renameVisible = ref(false);
const renameTarget = ref<{ id: string; name: string } | null>(null);
const renameName = ref("");

const renameMutation = useUpdateDatasetApiV1DatasetsDatasetIdPatch({
  mutation: {
    onSuccess: () => {
      message.success("Dataset renamed");
      qc.invalidateQueries({ queryKey: datasetListQueryPrefix.value });
      renameVisible.value = false;
      renameTarget.value = null;
      renameName.value = "";
    },
    onError: (error) => {
      message.error(toUserMessage(error, "Failed to rename dataset"));
    },
  },
});

function handleViewDataset(datasetId: string) {
  router.push(`/datasets/${datasetId}`);
}

function handleTogglePublic(payload: { id: string; isPublic: boolean }) {
  toggleDatasetPublicMut.mutate({
    datasetId: payload.id,
    data: { is_public: payload.isPublic },
  });
}

function handleDeleteDataset(row: DatasetListItem) {
  if (row.created_by !== authStore.user?.id) {
    message.error("Only the dataset creator can delete this dataset");
    return;
  }
  if (
    !window.confirm(
      `Delete dataset '${row.name}'? This removes its local jobs, samples, models, and Label Studio project.`,
    )
  ) {
    return;
  }
  deleteDatasetMut.mutate({ datasetId: row.id! });
}

function handleRenameDataset(row: DatasetListItem) {
  if (row.created_by !== authStore.user?.id) {
    message.error("Only the dataset creator can rename this dataset");
    return;
  }
  renameTarget.value = { id: row.id, name: row.name };
  renameName.value = row.name;
  renameVisible.value = true;
}

function submitRename(): false {
  const target = renameTarget.value;
  const name = renameName.value.trim();
  if (!target || !name) return false;
  renameMutation.mutate({ datasetId: target.id, data: { name } });
  return false;
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

const resolvedDatasetType = ref<string>();
const resolvedViewTypes = ref<string[]>();
watch(
  datasets,
  (items) => {
    const datasetType = getActiveDatasetType(items);
    const viewTypes = getActiveViewTypes(items);
    if (datasetType) resolvedDatasetType.value = datasetType;
    if (viewTypes) resolvedViewTypes.value = viewTypes;
  },
  { immediate: true },
);
watch(
  () => orgStore.currentOrgId,
  () => {
    resolvedDatasetType.value = undefined;
    resolvedViewTypes.value = undefined;
    keyword.value = "";
    creatorFilter.value = null;
    pagination.page = 1;
  },
);
const activeDatasetType = computed(
  () => getActiveDatasetType(datasets.value) ?? resolvedDatasetType.value,
);
const activeViewTypes = computed(
  () => getActiveViewTypes(datasets.value) ?? resolvedViewTypes.value,
);

const activeShim = computed(() =>
  resolveDatasetShim(activeDatasetType.value, activeViewTypes.value),
);
</script>

<style scoped>
.dataset-list-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin: 8px 0 12px;
}

.dataset-list-search {
  width: min(320px, 100%);
}

.dataset-list-creator {
  width: min(220px, 100%);
}
</style>
