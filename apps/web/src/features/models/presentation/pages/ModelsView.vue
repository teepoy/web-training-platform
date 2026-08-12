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
        <n-select
          v-model:value="creatorFilter"
          size="small"
          clearable
          filterable
          placeholder="Creator"
          :options="creatorOptions"
          class="models-creator"
        />
      </div>

      <n-data-table
        :columns="columns"
        :data="models"
        :bordered="false"
        :pagination="pagination"
        :row-key="(row: ModelResponse) => row.id"
        size="small"
        remote
      />
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
import type { DataTableColumns, PaginationProps } from "naive-ui";
import {
  NButton,
  NDataTable,
  NInput,
  NModal,
  NPopconfirm,
  NSelect,
  NSpace,
  NText,
  useMessage,
} from "naive-ui";
import type { ModelResponse } from "@/generated/orval/models";
import {
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

type ModelRow = ModelResponse & {
  created_by?: string | null;
  creator_name?: string | null;
};

const message = useMessage();
const queryClient = useQueryClient();
const authStore = useAuthStore();
const orgStore = useOrgStore();

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
const creatorFilter = ref<string | null>(null);
const modelListParams = computed(() => ({
  offset: ((pagination.page ?? 1) - 1) * (pagination.pageSize ?? 20),
  limit: pagination.pageSize ?? 20,
  q: debouncedKeyword.value.trim() || undefined,
  creator_id: creatorFilter.value ?? undefined,
}));
const modelListQueryKey = computed(() =>
  orgScopedQueryKey(
    orgStore.currentOrgId,
    getListModelsApiV1ModelsGetQueryKey(modelListParams.value),
  ),
);
const modelsQuery = useListModelsApiV1ModelsGet(modelListParams, {
  query: {
    queryKey: modelListQueryKey,
    enabled: computed(() => !!orgStore.currentOrgId),
    refetchInterval: 5000,
  },
});
const models = computed<ModelRow[]>(() => (modelsQuery.data.value?.items ?? []) as ModelRow[]);
const isLoading = computed(() => modelsQuery.isLoading.value);
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
const creatorOptions = computed(() =>
  (modelCreators.value ?? []).map((creator) => ({ label: creator.name, value: creator.id })),
);

watch([keyword, creatorFilter], () => {
  pagination.page = 1;
});

const renameVisible = ref(false);
const renameTarget = ref<ModelResponse | null>(null);
const renameName = ref("");

const modelsQueryKey = computed(() => orgScopedQueryKey(orgStore.currentOrgId, ["models"]));

const renameMutation = useUpdateModelApiV1ModelsModelIdPatch({
  mutation: {
    onSuccess: () => {
      message.success("Model renamed");
      queryClient.invalidateQueries({ queryKey: modelsQueryKey.value });
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
      queryClient.invalidateQueries({ queryKey: modelsQueryKey.value });
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
    title: "Model Name",
    key: "name",
    sorter: "default",
    render: (row) =>
      h(NText, { style: "font-weight: 500" }, { default: () => modelDisplayName(row) }),
  },
  {
    title: "Dataset",
    key: "dataset_name",
    ellipsis: { tooltip: true },
  },
  {
    title: "Trainer",
    key: "trainer_name",
    width: 160,
  },
  {
    title: "Creator",
    key: "creator_name",
    width: 160,
    sorter: (left, right) =>
      modelCreatorName(left).localeCompare(modelCreatorName(right), undefined, {
        numeric: true,
      }),
    render: (row) => modelCreatorName(row),
  },
  {
    title: "Created At",
    key: "created_at",
    width: 180,
    sorter: (left, right) =>
      new Date(left.created_at ?? 0).getTime() - new Date(right.created_at ?? 0).getTime(),
    render: (row) => (row.created_at ? new Date(row.created_at).toLocaleString() : "-"),
  },
  {
    title: "Actions",
    key: "actions",
    width: 160,
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

.models-creator {
  width: min(220px, 100%);
}
</style>
