<template>
  <div>
    <ResourcePageShell v-bind="surface.pageShellProps.value">
      <ResourceToolbar
        v-if="!props.embedded"
        :title="activeDatasetType === 'image_sc' ? t('datasets.patchTitle') : t('datasets.title')"
      />

      <ResourceFilterBar
        v-if="!props.embedded"
        :keyword="localKeyword"
        :keyword-placeholder="t('datasets.search')"
        :creator-scope="localCreatorScope"
        :creators="datasetCreators ?? []"
        :active-filter-count="activeFilterCount"
        :resource-label="t('resources.datasets')"
        @update:keyword="localKeyword = $event"
        @update:creator-scope="localCreatorScope = $event"
        @clear="clearFilters"
      />

      <BulkSelectionToolbar
        :selected-count="selectedDatasets.length"
        :item-label="t('datasets.item')"
        :loading="batchDeletePending"
        @clear="checkedDatasetIds = []"
      >
        <NButton
          size="small"
          type="error"
          :loading="batchDeletePending"
          @click="deleteSelectedDatasets"
        >
          {{ t("datasets.deleteSelected") }}
        </NButton>
      </BulkSelectionToolbar>

      <component
        :is="activeShim"
        :datasets="surface.datasets.value"
        :current-org-id="orgStore.currentOrgId"
        :current-user-id="authStore.user?.id ?? null"
        :is-superadmin="authStore.user?.is_superadmin ?? false"
        :checked-row-keys="checkedDatasetIds"
        :pagination="tablePagination"
        :sorter="sorter"
        @view="handleViewDataset"
        @toggle-public="handleTogglePublic"
        @delete="handleDeleteDataset"
        @rename="handleRenameDataset"
        @update:checked-row-keys="checkedDatasetIds = $event"
        @update:sorter="handleSorterChange"
      />
    </ResourcePageShell>

    <n-modal
      v-model:show="renameVisible"
      preset="dialog"
      :title="t('datasets.renameTitle')"
      :positive-text="t('common.save')"
      :negative-text="t('common.cancel')"
      :loading="renameMutation.isPending.value"
      @positive-click="submitRename"
      @negative-click="renameVisible = false"
    >
      <n-input
        v-model:value="renameName"
        :placeholder="t('datasets.newName')"
        maxlength="255"
        show-count
        @keyup.enter="submitRename"
      />
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useQueryClient } from "@tanstack/vue-query";
import {
  useMessage,
  NButton,
  NModal,
  NInput,
  type DataTableRowKey,
  type DataTableSortState,
} from "naive-ui";
import { useI18n } from "vue-i18n";
import { ResourcePageShell, ResourceToolbar } from "@/shared";
import {
  deleteDatasetApiV1DatasetsDatasetIdDelete,
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
import { useRemoteListState } from "@/shared/composables/useRemoteListState";
import BulkSelectionToolbar from "@/shared/components/bulk-selection-toolbar/BulkSelectionToolbar.vue";
import ResourceFilterBar from "@/shared/components/resource-filter-bar";
import { runBatchAction } from "@/shared/utils/runBatchAction";
import { resolveDatasetShim } from "./schema-registry";
import { resolveDatasetTaskType } from "./registry";
import { getActiveDatasetType, getActiveViewTypes } from "./selection";
import type { UserResponse as User } from "@/generated/orval/models";
import type { ListDatasetsApiV1DatasetsGetParams } from "@/generated/orval/models";
import type { DatasetListItem } from "@/shared/datasets/types";

const router = useRouter();
const { t } = useI18n();
const message = useMessage();
const qc = useQueryClient();
const orgStore = useOrgStore();
const authStore = useAuthStore();
const props = withDefaults(
  defineProps<{
    embedded?: boolean;
    search?: string;
    creatorId?: string | null;
  }>(),
  {
    embedded: false,
    search: "",
    creatorId: null,
  },
);
const localKeyword = ref("");
const localCreatorScope = ref("all");
const checkedDatasetIds = ref<DataTableRowKey[]>([]);
const batchDeletePending = ref(false);
const keyword = computed({
  get: () => (props.embedded ? props.search : localKeyword.value),
  set: (value: string) => {
    localKeyword.value = value;
  },
});
const localCreatorId = computed(() => {
  if (localCreatorScope.value === "all") return null;
  if (localCreatorScope.value === "me") return authStore.user?.id ?? null;
  return localCreatorScope.value;
});
const creatorFilter = computed(() => (props.embedded ? props.creatorId : localCreatorId.value));
const creatorFilterReady = computed(() =>
  props.embedded
    ? authStore.user !== null
    : localCreatorScope.value !== "me" || authStore.user !== null,
);
const total = ref(0);
const listState = useRemoteListState({
  keyword,
  filters: [creatorFilter, () => orgStore.currentOrgId],
  total,
  initialSorter: { columnKey: "created_at", order: "descend", sorter: true },
  onResetSelection: () => {
    checkedDatasetIds.value = [];
  },
});
const { debouncedKeyword, pagination, sorter, tablePagination } = listState;

const datasetListParams = computed<ListDatasetsApiV1DatasetsGetParams>(() => ({
  limit: pagination.pageSize ?? 20,
  offset: ((pagination.page ?? 1) - 1) * (pagination.pageSize ?? 20),
  q: debouncedKeyword.value.trim() || undefined,
  creator_id: creatorFilter.value ?? undefined,
  sort_by: datasetSortField(sorter.value?.columnKey),
  sort_order: sorter.value?.order === "ascend" ? ("asc" as const) : ("desc" as const),
}));

function datasetSortField(
  columnKey: DataTableSortState["columnKey"] | undefined,
): NonNullable<ListDatasetsApiV1DatasetsGetParams["sort_by"]> {
  if (columnKey === "name" || columnKey === "dataset_type" || columnKey === "creator") {
    return columnKey;
  }
  return "created_at" as const;
}

const handleSorterChange = listState.handleSorterChange;
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
  isLoading: datasetQueryLoading,
  error,
} = useListDatasetsApiV1DatasetsGet(datasetListParams, {
  query: {
    queryKey: datasetListQueryKey,
    enabled: computed(() => !!orgStore.currentOrgId && creatorFilterReady.value),
  },
});
const isLoading = computed(
  () => (!!orgStore.currentOrgId && !creatorFilterReady.value) || datasetQueryLoading.value,
);

const datasets = computed(() => datasetPage.value?.items ?? []);

const { data: datasetCreators } = useListDatasetCreatorsApiV1DatasetsCreatorsGet({
  query: {
    queryKey: computed(() => orgScopedQueryKey(orgStore.currentOrgId, ["datasets", "creators"])),
    enabled: computed(() => !props.embedded && !!orgStore.currentOrgId),
  },
});
watch(
  () => datasetPage.value?.total ?? 0,
  (nextTotal) => {
    total.value = nextTotal;
  },
  { immediate: true },
);

const activeFilterCount = computed(
  () => Number(localKeyword.value.trim().length > 0) + Number(localCreatorScope.value !== "all"),
);

function clearFilters(): void {
  localKeyword.value = "";
  localCreatorScope.value = "all";
}

const toggleDatasetPublicMut = useSetDatasetPublicApiV1DatasetsDatasetIdPublicPatch({
  mutation: {
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: datasetListQueryPrefix.value });
    },
    onError: (error) => {
      message.error(toUserMessage(error, t("datasets.visibilityFailed")));
    },
  },
});

const deleteDatasetMut = useDeleteDatasetApiV1DatasetsDatasetIdDelete({
  mutation: {
    onSuccess: () => {
      message.success(t("datasets.deleted"));
      qc.invalidateQueries({ queryKey: datasetListQueryPrefix.value });
    },
    onError: (error) => {
      message.error(toUserMessage(error, t("datasets.deleteFailed")));
    },
  },
});

const renameVisible = ref(false);
const renameTarget = ref<{ id: string; name: string } | null>(null);
const renameName = ref("");

const renameMutation = useUpdateDatasetApiV1DatasetsDatasetIdPatch({
  mutation: {
    onSuccess: () => {
      message.success(t("datasets.renamed"));
      qc.invalidateQueries({ queryKey: datasetListQueryPrefix.value });
      renameVisible.value = false;
      renameTarget.value = null;
      renameName.value = "";
    },
    onError: (error) => {
      message.error(toUserMessage(error, t("datasets.renameFailed")));
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
    message.error(t("datasets.creatorDeleteOnly"));
    return;
  }
  if (!window.confirm(t("datasets.confirmDelete", { name: row.name }))) {
    return;
  }
  deleteDatasetMut.mutate({ datasetId: row.id! });
}

function handleRenameDataset(row: DatasetListItem) {
  if (row.created_by !== authStore.user?.id) {
    message.error(t("datasets.creatorRenameOnly"));
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

const selectedDatasets = computed(() => {
  const selectedIds = new Set(checkedDatasetIds.value.map(String));
  return surface.datasets.value.filter(
    (dataset) => selectedIds.has(dataset.id) && dataset.created_by === (authStore.user?.id ?? null),
  );
});

async function deleteSelectedDatasets(): Promise<void> {
  const selected = [...selectedDatasets.value];
  if (selected.length === 0 || batchDeletePending.value) return;
  if (
    !window.confirm(
      t("datasets.confirmDeleteSelected", { count: selected.length }, selected.length),
    )
  ) {
    return;
  }

  batchDeletePending.value = true;
  try {
    const result = await runBatchAction(selected, (dataset) =>
      deleteDatasetApiV1DatasetsDatasetIdDelete(dataset.id),
    );
    checkedDatasetIds.value = result.failed.map(({ item }) => item.id);
    if (result.succeeded.length > 0) {
      await qc.invalidateQueries({ queryKey: datasetListQueryPrefix.value });
    }
    if (result.failed.length === 0) {
      message.success(
        t("datasets.deletedCount", { count: result.succeeded.length }, result.succeeded.length),
      );
    } else if (result.succeeded.length === 0) {
      message.error(toUserMessage(result.failed[0]?.error, t("datasets.deleteSelectedFailed")));
    } else {
      message.warning(
        t("datasets.partialDelete", {
          deleted: result.succeeded.length,
          failed: result.failed.length,
        }),
      );
    }
  } finally {
    batchDeletePending.value = false;
  }
}

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
    if (!props.embedded) localKeyword.value = "";
    pagination.page = 1;
    checkedDatasetIds.value = [];
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
