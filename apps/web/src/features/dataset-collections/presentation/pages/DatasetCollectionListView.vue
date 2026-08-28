<script setup lang="ts">
import { computed, h, reactive, ref, watch } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { refDebounced } from "@vueuse/core";
import { useRouter } from "vue-router";
import {
  NButton,
  NAlert,
  NCard,
  NDataTable,
  NEmpty,
  NFormItem,
  NInput,
  NModal,
  NSelect,
  NSpace,
  NTag,
  NText,
  useMessage,
  type DataTableColumns,
  type DataTableRowKey,
  type DataTableSortState,
  type PaginationProps,
} from "naive-ui";
import {
  deleteCollectionApiV1DatasetCollectionsCollectionIdDelete,
  listCollectionsApiV1DatasetCollectionsGet,
  listDatasetsApiV1DatasetsGet,
} from "@/generated/orval/endpoints/api";
import type { Dataset, DatasetCollectionResponse } from "@/generated/orval/models";
import {
  createCollectionWithMembers,
  haveMatchingOrderedLabelSpaces,
} from "@/features/dataset-collections/application/createCollectionWithMembers";
import { useOrgStore } from "@/features/auth/application/org";
import { useAuthStore } from "@/features/auth/application/store";
import { orgScopedQueryKey, toUserMessage } from "@/shared/api";
import { useDefaultCreatorFilter } from "@/shared/composables/useDefaultCreatorFilter";
import BulkSelectionToolbar from "@/shared/components/bulk-selection-toolbar/BulkSelectionToolbar.vue";
import { runBatchAction } from "@/shared/utils/runBatchAction";

const router = useRouter();
const queryClient = useQueryClient();
const message = useMessage();
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
const debouncedSearch = refDebounced(
  computed(() => props.search),
  250,
);
const { creatorFilter: localCreatorFilter, isReady: localCreatorFilterReady } =
  useDefaultCreatorFilter(
    () => orgStore.currentOrgId,
    () => authStore.user?.id,
  );
const creatorFilter = computed({
  get: () => (props.embedded ? props.creatorId : localCreatorFilter.value),
  set: (value: string | null) => {
    localCreatorFilter.value = value;
  },
});
const creatorFilterReady = computed(() =>
  props.embedded ? authStore.user !== null : localCreatorFilterReady.value,
);
const createVisible = ref(false);
const name = ref("");
const description = ref("");
const targetViewId = ref<string | null>(null);
const selectedDatasetIds = ref<string[]>([]);
const checkedCollectionIds = ref<DataTableRowKey[]>([]);
const sorter = ref<DataTableSortState | null>({
  columnKey: "updated_at",
  order: "descend",
  sorter: true,
});
const batchDeletePending = ref(false);
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

async function loadAllDatasets(): Promise<Dataset[]> {
  const datasets: Dataset[] = [];
  while (true) {
    const page = await listDatasetsApiV1DatasetsGet({ offset: datasets.length, limit: 200 });
    datasets.push(...page.items);
    if (datasets.length >= page.total || page.items.length === 0) return datasets;
  }
}

const collectionsQuery = useQuery({
  queryKey: computed(() =>
    orgScopedQueryKey(orgStore.currentOrgId, [
      "dataset-collections",
      pagination.page,
      pagination.pageSize,
      creatorFilter.value,
      debouncedSearch.value,
      sorter.value?.columnKey ?? "updated_at",
      sorter.value?.order ?? "descend",
    ]),
  ),
  queryFn: () =>
    listCollectionsApiV1DatasetCollectionsGet({
      offset: ((pagination.page ?? 1) - 1) * (pagination.pageSize ?? 20),
      limit: pagination.pageSize ?? 20,
      creator_id: creatorFilter.value ?? undefined,
      q: debouncedSearch.value.trim() || undefined,
      sort_by: collectionSortField(sorter.value?.columnKey),
      sort_order: sorter.value?.order === "ascend" ? "asc" : "desc",
    }),
  enabled: computed(() => !!orgStore.currentOrgId && creatorFilterReady.value),
});
const datasetsQuery = useQuery({
  queryKey: computed(() => orgScopedQueryKey(orgStore.currentOrgId, ["datasets", "all"])),
  queryFn: loadAllDatasets,
  enabled: computed(() => !!orgStore.currentOrgId),
});
const collections = computed(() => collectionsQuery.data.value?.items ?? []);

function collectionSortField(columnKey: DataTableSortState["columnKey"] | undefined) {
  if (columnKey === "name" || columnKey === "creator" || columnKey === "created_at") {
    return columnKey;
  }
  return "updated_at" as const;
}

function handleSorterChange(value: DataTableSortState | DataTableSortState[] | null): void {
  sorter.value = Array.isArray(value) ? (value[0] ?? null) : value;
  pagination.page = 1;
  checkedCollectionIds.value = [];
}
const tablePagination = computed(() =>
  (pagination.itemCount ?? 0) > (pagination.pageSize ?? 20) ? pagination : false,
);
const datasets = computed(() => datasetsQuery.data.value ?? []);
const selectedDatasets = computed(() =>
  datasets.value.filter((dataset) => selectedDatasetIds.value.includes(String(dataset.id ?? ""))),
);
const labelSpacesCompatible = computed(() =>
  haveMatchingOrderedLabelSpaces(selectedDatasets.value),
);

watch(
  () => collectionsQuery.data.value?.total ?? 0,
  (total) => {
    pagination.itemCount = total;
  },
  { immediate: true },
);

watch([creatorFilter, debouncedSearch], () => {
  pagination.page = 1;
  checkedCollectionIds.value = [];
});

watch(
  () => [pagination.page, pagination.pageSize, orgStore.currentOrgId],
  () => {
    checkedCollectionIds.value = [];
  },
);

const creatorOptions = computed(() => {
  const user = authStore.user;
  return user ? [{ label: user.name || user.email || user.id, value: user.id }] : [];
});

const emptyDescription = computed(() =>
  debouncedSearch.value.trim()
    ? "No dataset collections match this search"
    : creatorFilter.value
      ? "You have not created any dataset collections yet"
      : "No dataset collections have been created yet",
);

const targetViewOptions = computed(() => {
  const selected = selectedDatasets.value;
  if (selected.length === 0) {
    return [...new Set(datasets.value.flatMap((dataset) => dataset.view_types ?? []))]
      .sort()
      .map((view) => ({ label: view, value: view }));
  }
  const intersection = selected.reduce<Set<string> | null>((result, dataset) => {
    const views = new Set(dataset.view_types ?? []);
    return result === null ? views : new Set([...result].filter((view) => views.has(view)));
  }, null);
  return [...(intersection ?? new Set<string>())].sort().map((view) => ({
    label: view,
    value: view,
  }));
});

watch(targetViewOptions, (options) => {
  if (targetViewId.value && options.some((option) => option.value === targetViewId.value)) return;
  targetViewId.value = null;
});

const datasetOptions = computed(() =>
  datasets.value
    .filter(
      (dataset) => !targetViewId.value || (dataset.view_types ?? []).includes(targetViewId.value),
    )
    .map((dataset) => ({
      label: dataset.name,
      value: String(dataset.id ?? ""),
    }))
    .filter((option) => option.value.length > 0),
);

const createMutation = useMutation({
  mutationFn: () =>
    createCollectionWithMembers({
      name: name.value.trim(),
      description: description.value.trim(),
      targetViewId: targetViewId.value ?? "",
      sourceDatasetIds: selectedDatasetIds.value,
    }),
  onSuccess: async (collection) => {
    message.success("Dataset collection created");
    createVisible.value = false;
    await queryClient.invalidateQueries({
      queryKey: orgScopedQueryKey(orgStore.currentOrgId, ["dataset-collections"]),
    });
    await router.push(`/dataset-collections/${collection.id}`);
  },
  onError: (error) => message.error(toUserMessage(error, "Failed to create collection")),
});

const canCreate = computed(
  () => name.value.trim().length > 0 && !!targetViewId.value && labelSpacesCompatible.value,
);

function openCreate(): void {
  name.value = "";
  description.value = "";
  targetViewId.value = null;
  selectedDatasetIds.value = [];
  createVisible.value = true;
}

defineExpose({ openCreate });

function collectionRowProps(row: DatasetCollectionResponse): Record<string, unknown> {
  return {
    style: "cursor: pointer",
    onClick: (event: MouseEvent) => {
      const target = event.target;
      if (
        target instanceof Element &&
        target.closest("button, a, input, [role='checkbox'], [data-stop-row-click]")
      ) {
        return;
      }
      void router.push(`/dataset-collections/${row.id}`);
    },
  };
}

const selectedCollections = computed(() => {
  const selectedIds = new Set(checkedCollectionIds.value.map(String));
  return collections.value.filter(
    (collection) => selectedIds.has(collection.id) && collection.created_by === authStore.user?.id,
  );
});

async function deleteSelectedCollections(): Promise<void> {
  const selected = [...selectedCollections.value];
  if (selected.length === 0 || batchDeletePending.value) return;
  if (
    !window.confirm(
      `Delete ${selected.length} selected collection${selected.length === 1 ? "" : "s"}? Their saved snapshots will also be removed; source datasets are not changed.`,
    )
  ) {
    return;
  }

  batchDeletePending.value = true;
  try {
    const result = await runBatchAction(selected, (collection) =>
      deleteCollectionApiV1DatasetCollectionsCollectionIdDelete(collection.id),
    );
    checkedCollectionIds.value = result.failed.map(({ item }) => item.id);
    if (result.succeeded.length > 0) {
      await queryClient.invalidateQueries({
        queryKey: orgScopedQueryKey(orgStore.currentOrgId, ["dataset-collections"]),
      });
    }
    if (result.failed.length === 0) {
      message.success(
        `${result.succeeded.length} collection${result.succeeded.length === 1 ? "" : "s"} deleted`,
      );
    } else if (result.succeeded.length === 0) {
      message.error(
        toUserMessage(result.failed[0]?.error, "Failed to delete selected collections"),
      );
    } else {
      message.warning(
        `${result.succeeded.length} deleted; ${result.failed.length} could not be deleted and remain selected`,
      );
    }
  } finally {
    batchDeletePending.value = false;
  }
}

const columns = computed<DataTableColumns<DatasetCollectionResponse>>(() => [
  {
    type: "selection",
    fixed: "left",
    disabled: (row) => row.created_by !== authStore.user?.id,
  },
  {
    title: "Name",
    key: "name",
    minWidth: 180,
    sorter: true,
    sortOrder: sorter.value?.columnKey === "name" ? sorter.value.order : false,
  },
  { title: "Target view", key: "target_view_id", minWidth: 160 },
  {
    title: "Definition",
    key: "definition_version",
    render: (row) => `v${row.definition_version}`,
  },
  {
    title: "Creator",
    key: "creator",
    minWidth: 130,
    sorter: true,
    sortOrder: sorter.value?.columnKey === "creator" ? sorter.value.order : false,
    render: (row) =>
      row.created_by === authStore.user?.id
        ? authStore.user?.name || authStore.user?.email || "You"
        : row.creator_name?.trim() || row.created_by,
  },
  {
    title: "Policy",
    key: "duplicate_policy",
    render: () => h(NTag, { size: "small" }, { default: () => "Keep all samples" }),
  },
  {
    title: "Updated",
    key: "updated_at",
    width: 180,
    sorter: true,
    sortOrder: sorter.value?.columnKey === "updated_at" ? sorter.value.order : false,
    render: (row) => new Date(row.updated_at).toLocaleString(),
  },
  {
    title: "",
    key: "actions",
    width: 90,
    fixed: "right",
    render: (row) =>
      h(
        NButton,
        {
          size: "small",
          onClick: (event: Event) => {
            event.stopPropagation();
            void router.push(`/dataset-collections/${row.id}`);
          },
        },
        { default: () => "Open" },
      ),
  },
]);
</script>

<template>
  <div class="collection-list-page" :class="{ 'collection-list-page--embedded': props.embedded }">
    <div v-if="!props.embedded" class="collection-list-header">
      <div>
        <h1>Dataset Collections</h1>
        <NText depth="3">Dynamically compose existing datasets without changing them.</NText>
      </div>
      <NButton type="primary" :disabled="!orgStore.currentOrgId" @click="openCreate">
        New collection
      </NButton>
    </div>

    <NCard
      :bordered="!props.embedded"
      :content-style="props.embedded ? { padding: '0' } : undefined"
    >
      <div v-if="!props.embedded" class="collection-list-filters">
        <NSelect
          v-model:value="creatorFilter"
          size="small"
          clearable
          placeholder="All creators"
          :options="creatorOptions"
          class="collection-list-creator"
        />
        <NText depth="3">Clear the creator filter to view collections from everyone.</NText>
      </div>
      <BulkSelectionToolbar
        :selected-count="selectedCollections.length"
        item-label="collection"
        :loading="batchDeletePending"
        @clear="checkedCollectionIds = []"
      >
        <NButton
          size="small"
          type="error"
          :loading="batchDeletePending"
          @click="deleteSelectedCollections"
        >
          Delete selected
        </NButton>
      </BulkSelectionToolbar>
      <NAlert v-if="collectionsQuery.isError.value" type="error" style="margin-bottom: 12px">
        {{ toUserMessage(collectionsQuery.error.value, "Failed to load dataset collections") }}
      </NAlert>
      <template v-if="!orgStore.currentOrgId">
        <NEmpty description="Select or join an organization to manage dataset collections" />
      </template>
      <NDataTable
        v-else-if="!collectionsQuery.isError.value"
        :columns="columns"
        :data="collections"
        :loading="collectionsQuery.isLoading.value || !creatorFilterReady"
        :pagination="tablePagination"
        :row-key="(row: DatasetCollectionResponse) => row.id"
        :row-props="collectionRowProps"
        :checked-row-keys="checkedCollectionIds"
        :scroll-x="820"
        remote
        @update:checked-row-keys="checkedCollectionIds = $event"
        @update:sorter="handleSorterChange"
      >
        <template #empty>
          <NEmpty :description="emptyDescription">
            <template #extra>
              <NButton @click="openCreate">Create a collection</NButton>
            </template>
          </NEmpty>
        </template>
      </NDataTable>
      <NText v-if="collections.length > 0" class="mobile-table-hint" depth="3">
        Tap a row to open it. Swipe sideways for more columns.
      </NText>
    </NCard>

    <NModal
      v-model:show="createVisible"
      preset="card"
      title="Create dataset collection"
      class="collection-modal"
      :style="{ width: 'min(620px, calc(100vw - 32px))' }"
    >
      <NFormItem label="Name" required>
        <NInput v-model:value="name" placeholder="Collection name" maxlength="255" />
      </NFormItem>
      <NFormItem label="Description">
        <NInput v-model:value="description" type="textarea" placeholder="Purpose and scope" />
      </NFormItem>
      <NFormItem label="Existing datasets">
        <NSelect
          v-model:value="selectedDatasetIds"
          multiple
          filterable
          clearable
          :options="datasetOptions"
          :loading="datasetsQuery.isLoading.value"
          placeholder="Select datasets to link now, or leave empty"
        />
      </NFormItem>
      <NText class="field-help" depth="3">
        Pick datasets first to narrow the target views to the ones they all support.
      </NText>
      <NAlert v-if="!labelSpacesCompatible" type="error" :show-icon="false">
        Selected datasets must use the same labels in the same order.
      </NAlert>
      <NFormItem label="Target view" required>
        <NSelect
          v-model:value="targetViewId"
          :options="targetViewOptions"
          :disabled="targetViewOptions.length === 0"
          placeholder="Choose a view supported by every selected dataset"
        />
      </NFormItem>
      <NText depth="3">
        Linked datasets remain standalone. Save the current setup before using it for review,
        training, or prediction; member data is read when each run starts.
      </NText>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="createVisible = false">Cancel</NButton>
          <NButton
            type="primary"
            :disabled="!canCreate"
            :loading="createMutation.isPending.value"
            @click="createMutation.mutate()"
          >
            Create
          </NButton>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.collection-list-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.collection-list-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.collection-list-page--embedded {
  gap: 0;
}

h1 {
  margin: 0 0 4px;
  font-size: 24px;
}

.field-help {
  display: block;
  margin: -12px 0 14px;
  font-size: 12px;
}

.collection-list-filters {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.collection-list-creator {
  width: min(220px, 100%);
}

.mobile-table-hint {
  display: none;
}

@media (max-width: 640px) {
  .collection-list-header {
    align-items: stretch;
    flex-direction: column;
  }

  .collection-list-header :deep(.n-button) {
    width: 100%;
  }

  .collection-list-filters {
    align-items: stretch;
    flex-direction: column;
  }

  .collection-list-creator {
    width: 100%;
  }

  .mobile-table-hint {
    display: block;
    margin-top: 10px;
    font-size: 12px;
  }
}
</style>
