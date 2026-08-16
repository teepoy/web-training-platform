<template>
  <DatasetPageShell :is-loading="isLoading" :has-org="!!orgStore.currentOrgId" :error="error">
    <div class="models-view">
      <DatasetToolbar title="Models" />

      <div class="models-list-filters">
        <n-input
          v-model:value="keyword"
          size="small"
          clearable
          placeholder="Search models"
          class="models-search"
        />
        <n-text depth="3">
          Use the Training Source and Creator column filters to narrow results.
        </n-text>
      </div>

      <BulkSelectionToolbar
        :selected-count="selectedModels.length"
        item-label="model"
        :loading="batchDeletePending"
        @clear="checkedModelIds = []"
      >
        <NButton
          size="small"
          type="error"
          :loading="batchDeletePending"
          @click="deleteSelectedModels"
        >
          Delete selected
        </NButton>
      </BulkSelectionToolbar>

      <n-data-table
        :columns="columns"
        :data="models"
        :bordered="false"
        :pagination="tablePagination"
        :row-key="(row: ModelResponse) => row.id"
        :checked-row-keys="checkedModelIds"
        :sorter="sorter"
        :filters="tableFilters"
        :scroll-x="980"
        size="small"
        remote
        @update:checked-row-keys="checkedModelIds = $event"
        @update:sorter="handleSorterChange"
        @update:filters="handleFiltersChange"
      >
        <template #empty>
          <n-empty :description="emptyDescription" />
        </template>
      </n-data-table>
      <n-text v-if="models.length > 0" class="mobile-table-hint" depth="3">
        Swipe sideways to see model details and management actions.
      </n-text>
    </div>

    <n-modal
      v-model:show="renameVisible"
      preset="dialog"
      title="Rename Model"
      positive-text="Save"
      negative-text="Cancel"
      :loading="renameMutation.isPending.value"
      @positive-click="submitRename"
      @negative-click="resetRename"
    >
      <n-input v-model:value="renameName" placeholder="Model name" maxlength="255" show-count />
    </n-modal>
  </DatasetPageShell>
</template>

<script setup lang="ts">
import { computed, h, reactive, ref, watch } from "vue";
import { useQueryClient } from "@tanstack/vue-query";
import { refDebounced } from "@vueuse/core";
import { useRouter } from "vue-router";
import type {
  DataTableColumns,
  DataTableFilterState,
  DataTableRowKey,
  DataTableSortState,
  PaginationProps,
} from "naive-ui";
import {
  NButton,
  NDataTable,
  NInput,
  NModal,
  NPopconfirm,
  NSpace,
  NText,
  useMessage,
} from "naive-ui";
import type { ListModelsApiV1ModelsGetParams, ModelResponse } from "@/generated/orval/models";
import {
  deleteModelApiV1ModelsModelIdDelete,
  useDeleteModelApiV1ModelsModelIdDelete,
  getListModelsApiV1ModelsGetQueryKey,
  useListModelCreatorsApiV1ModelsCreatorsGet,
  useListModelsApiV1ModelsGet,
  useUpdateModelApiV1ModelsModelIdPatch,
} from "@/generated/orval/endpoints/api";
import { orgScopedQueryKey, toUserMessage } from "@/shared/api";
import { DatasetPageShell, DatasetToolbar } from "@/shared";
import { useAuthStore } from "@/features/auth/application/store";
import { useOrgStore } from "@/features/auth/application/org";
import { useDefaultCreatorFilter } from "@/shared/composables/useDefaultCreatorFilter";
import BulkSelectionToolbar from "@/shared/components/bulk-selection-toolbar/BulkSelectionToolbar.vue";
import { runBatchAction } from "@/shared/utils/runBatchAction";

type ModelRow = ModelResponse & {
  created_by?: string | null;
  creator_name?: string | null;
};

const message = useMessage();
const queryClient = useQueryClient();
const router = useRouter();
const authStore = useAuthStore();
const orgStore = useOrgStore();
const checkedModelIds = ref<DataTableRowKey[]>([]);
const batchDeletePending = ref(false);
const sorter = ref<DataTableSortState | null>({
  columnKey: "created_at",
  order: "descend",
  sorter: true,
});
const sourceTypeFilter = ref<"dataset" | "collection" | null>(null);

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

const keyword = ref("");
const debouncedKeyword = refDebounced(keyword, 250);
const { creatorFilter, isReady: creatorFilterReady } = useDefaultCreatorFilter(
  () => orgStore.currentOrgId,
  () => authStore.user?.id,
);
const modelListParams = computed<ListModelsApiV1ModelsGetParams>(() => ({
  offset: ((pagination.page ?? 1) - 1) * (pagination.pageSize ?? 20),
  limit: pagination.pageSize ?? 20,
  q: debouncedKeyword.value.trim() || undefined,
  creator_id: creatorFilter.value ?? undefined,
  source_type: sourceTypeFilter.value ?? undefined,
  sort_by: modelSortField(sorter.value?.columnKey),
  sort_order: sorter.value?.order === "ascend" ? ("asc" as const) : ("desc" as const),
}));

function modelSortField(
  columnKey: DataTableSortState["columnKey"] | undefined,
): NonNullable<ListModelsApiV1ModelsGetParams["sort_by"]> {
  if (
    columnKey === "name" ||
    columnKey === "source" ||
    columnKey === "trainer" ||
    columnKey === "creator"
  ) {
    return columnKey;
  }
  return "created_at" as const;
}
const modelListQueryKey = computed(() =>
  orgScopedQueryKey(
    orgStore.currentOrgId,
    getListModelsApiV1ModelsGetQueryKey(modelListParams.value),
  ),
);
const modelsQuery = useListModelsApiV1ModelsGet(modelListParams, {
  query: {
    queryKey: modelListQueryKey,
    enabled: computed(() => !!orgStore.currentOrgId && creatorFilterReady.value),
    refetchInterval: 5000,
  },
});
const models = computed<ModelRow[]>(() => (modelsQuery.data.value?.items ?? []) as ModelRow[]);
const tablePagination = computed(() =>
  (pagination.itemCount ?? 0) > (pagination.pageSize ?? 20) ? pagination : false,
);
const emptyDescription = computed(() =>
  keyword.value.trim() || creatorFilter.value || sourceTypeFilter.value
    ? "No models match the current filters"
    : "No models have been created yet",
);
const isLoading = computed(
  () => (!!orgStore.currentOrgId && !creatorFilterReady.value) || modelsQuery.isLoading.value,
);
const error = computed(() => (modelsQuery.error.value as Error | null) ?? null);

watch(
  () => modelsQuery.data.value?.total ?? 0,
  (total) => {
    pagination.itemCount = total;
  },
  { immediate: true },
);

const { data: modelCreators } = useListModelCreatorsApiV1ModelsCreatorsGet({
  query: {
    queryKey: computed(() => orgScopedQueryKey(orgStore.currentOrgId, ["models", "creators"])),
    enabled: computed(() => !!orgStore.currentOrgId),
  },
});
const creatorOptions = computed(() => {
  const options = (modelCreators.value ?? []).map((creator) => ({
    label: creator.name,
    value: creator.id,
  }));
  const user = authStore.user;
  if (user && !options.some((option) => option.value === user.id)) {
    options.unshift({ label: user.name || user.email || user.id, value: user.id });
  }
  return options;
});

watch([keyword, creatorFilter, sourceTypeFilter], () => {
  pagination.page = 1;
  checkedModelIds.value = [];
});

const tableFilters = computed<DataTableFilterState>(() => ({
  source: sourceTypeFilter.value,
  creator: creatorFilter.value,
}));

function firstFilterValue(value: DataTableFilterState[string]): string | null {
  const resolved = Array.isArray(value) ? value[0] : value;
  return typeof resolved === "string" ? resolved : null;
}

function handleFiltersChange(filters: DataTableFilterState): void {
  const source = firstFilterValue(filters.source);
  sourceTypeFilter.value = source === "dataset" || source === "collection" ? source : null;
  creatorFilter.value = firstFilterValue(filters.creator);
}

function handleSorterChange(value: DataTableSortState | DataTableSortState[] | null): void {
  sorter.value = Array.isArray(value) ? (value[0] ?? null) : value;
  pagination.page = 1;
  checkedModelIds.value = [];
}

watch(
  () => [pagination.page, pagination.pageSize, orgStore.currentOrgId],
  () => {
    checkedModelIds.value = [];
  },
);

const renameVisible = ref(false);
const renameTarget = ref<ModelResponse | null>(null);
const renameName = ref("");

const modelsApiQueryKey = computed(() =>
  orgScopedQueryKey(orgStore.currentOrgId, ["api", "v1", "models"]),
);
const modelsUiQueryKey = computed(() => orgScopedQueryKey(orgStore.currentOrgId, ["models"]));

function invalidateModelQueries(): void {
  void queryClient.invalidateQueries({ queryKey: modelsApiQueryKey.value });
  void queryClient.invalidateQueries({ queryKey: modelsUiQueryKey.value });
}

const selectedModels = computed(() => {
  const selectedIds = new Set(checkedModelIds.value.map(String));
  return models.value.filter(
    (model) => selectedIds.has(model.id) && model.created_by === authStore.user?.id,
  );
});

async function deleteSelectedModels(): Promise<void> {
  const selected = [...selectedModels.value];
  if (selected.length === 0 || batchDeletePending.value) return;
  if (
    !window.confirm(
      `Delete ${selected.length} selected model${selected.length === 1 ? "" : "s"}? Stored model artifacts will also be removed.`,
    )
  ) {
    return;
  }

  batchDeletePending.value = true;
  try {
    const result = await runBatchAction(selected, (model) =>
      deleteModelApiV1ModelsModelIdDelete(model.id),
    );
    checkedModelIds.value = result.failed.map(({ item }) => item.id);
    if (result.succeeded.length > 0) invalidateModelQueries();
    if (result.failed.length === 0) {
      message.success(
        `${result.succeeded.length} model${result.succeeded.length === 1 ? "" : "s"} deleted`,
      );
    } else if (result.succeeded.length === 0) {
      message.error(toUserMessage(result.failed[0]?.error, "Failed to delete selected models"));
    } else {
      message.warning(
        `${result.succeeded.length} deleted; ${result.failed.length} could not be deleted and remain selected`,
      );
    }
  } finally {
    batchDeletePending.value = false;
  }
}

const renameMutation = useUpdateModelApiV1ModelsModelIdPatch({
  mutation: {
    onSuccess: () => {
      message.success("Model renamed");
      invalidateModelQueries();
      resetRename();
    },
    onError: (error) => {
      message.error(toUserMessage(error, "Failed to rename model"));
    },
  },
});

const deleteMutation = useDeleteModelApiV1ModelsModelIdDelete({
  mutation: {
    onSuccess: () => {
      message.success("Model deleted");
      invalidateModelQueries();
    },
    onError: (error) => {
      message.error(toUserMessage(error, "Failed to delete model"));
    },
  },
});

function modelDisplayName(row: ModelResponse): string {
  return row.name?.trim() || row.id.slice(0, 8);
}

function modelCreatorName(row: ModelRow): string {
  return row.creator_name?.trim() || row.created_by?.trim() || "system";
}

function modelSourceName(row: ModelRow): string {
  if (row.dataset_id) return row.dataset_name?.trim() || row.dataset_id.slice(0, 8);
  if (row.collection_id) return row.collection_name?.trim() || row.collection_id.slice(0, 8);
  return row.dataset_name?.trim() || row.collection_name?.trim() || "—";
}

function openModelSource(row: ModelRow): void {
  if (row.dataset_id) {
    void router.push(`/datasets/${row.dataset_id}`);
    return;
  }
  if (row.collection_id) {
    void router.push(`/dataset-collections/${row.collection_id}`);
  }
}

function openRename(row: ModelRow): void {
  if (row.created_by !== authStore.user?.id) {
    message.error("Only the model creator can rename this model");
    return;
  }
  renameTarget.value = row;
  renameName.value = modelDisplayName(row);
  renameVisible.value = true;
}

function resetRename(): void {
  renameVisible.value = false;
  renameTarget.value = null;
  renameName.value = "";
}

function submitRename(): false {
  const target = renameTarget.value;
  const name = renameName.value.trim();
  if (!target || !name) return false;
  renameMutation.mutate({ modelId: target.id, data: { name } });
  return false;
}

const columns = computed<DataTableColumns<ModelRow>>(() => [
  {
    type: "selection",
    disabled: (row) => row.created_by !== authStore.user?.id,
  },
  {
    title: "Model Name",
    key: "name",
    width: 170,
    sorter: true,
    render: (row) =>
      h(NText, { style: "font-weight: 500" }, { default: () => modelDisplayName(row) }),
  },
  {
    title: "Training Source",
    key: "source",
    width: 210,
    sorter: true,
    filter: true,
    filterMultiple: false,
    filterOptions: [
      { label: "Dataset", value: "dataset" },
      { label: "Collection", value: "collection" },
    ],
    filterOptionValue: sourceTypeFilter.value,
    render: (row) =>
      row.dataset_id || row.collection_id
        ? h(
            NButton,
            {
              text: true,
              type: "primary",
              size: "small",
              onClick: () => openModelSource(row),
            },
            {
              default: () =>
                `${row.dataset_id ? "Dataset" : "Collection"} · ${modelSourceName(row)}`,
            },
          )
        : h(NText, { depth: 3 }, { default: () => modelSourceName(row) }),
  },
  {
    title: "Trainer",
    key: "trainer",
    width: 150,
    sorter: true,
  },
  {
    title: "Creator",
    key: "creator",
    width: 130,
    sorter: true,
    filter: true,
    filterMultiple: false,
    filterOptions: creatorOptions.value,
    filterOptionValue: creatorFilter.value,
    render: (row) => modelCreatorName(row),
  },
  {
    title: "Created At",
    key: "created_at",
    width: 170,
    sorter: true,
    render: (row) => (row.created_at ? new Date(row.created_at).toLocaleString() : "-"),
  },
  {
    title: "Actions",
    key: "actions",
    width: 150,
    render: (row) => {
      const isCreator = row.created_by === authStore.user?.id;
      return h(
        NSpace,
        { size: 6, wrap: false },
        {
          default: () => [
            h(
              NButton,
              {
                size: "small",
                quaternary: true,
                disabled: !isCreator,
                onClick: () => openRename(row),
              },
              { default: () => "Rename" },
            ),
            isCreator
              ? h(
                  NPopconfirm,
                  {
                    onPositiveClick: () => deleteMutation.mutate({ modelId: row.id }),
                  },
                  {
                    trigger: () =>
                      h(
                        NButton,
                        {
                          size: "small",
                          quaternary: true,
                          type: "error",
                          loading:
                            deleteMutation.isPending.value &&
                            deleteMutation.variables.value?.modelId === row.id,
                        },
                        { default: () => "Delete" },
                      ),
                    default: () => `Delete model '${modelDisplayName(row)}'?`,
                  },
                )
              : null,
          ],
        },
      );
    },
  },
]);
</script>

<style scoped>
.models-view {
  height: 100%;
}

.models-list-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin: 8px 0 12px;
}

.models-search {
  width: min(320px, 100%);
}

.mobile-table-hint {
  display: none;
}

@media (max-width: 640px) {
  .models-list-filters {
    align-items: stretch;
    flex-direction: column;
  }

  .models-search,
  .mobile-table-hint {
    display: block;
    margin-top: 10px;
    font-size: 12px;
  }
}
</style>
