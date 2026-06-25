<template>
  <n-space vertical size="large" class="models-view">
    <n-page-header title="Models" />
    <n-input
      v-model:value="keyword"
      size="small"
      clearable
      placeholder="Search models"
      class="models-search"
    />
    <n-data-table
      :columns="columns"
      :data="filteredModels"
      :loading="isLoading"
      :bordered="false"
      :pagination="pagination"
      :row-key="(row: ModelResponse) => row.id"
      size="small"
    />

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
      <n-input
        v-model:value="renameName"
        placeholder="Model name"
        maxlength="255"
        show-count
      />
    </n-modal>
  </n-space>
</template>

<script setup lang="ts">
import { computed, h, reactive, ref, watch } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import type { DataTableColumns, PaginationProps } from "naive-ui";
import {
  NButton,
  NDataTable,
  NInput,
  NModal,
  NPageHeader,
  NPopconfirm,
  NSpace,
  NText,
  useMessage,
} from "naive-ui";
import type { ModelResponse } from "@/generated/orval/models";
import { deleteModel, listModels, renameModel } from "@/shared/api/models";

type ModelRow = ModelResponse & {
  created_by?: string | null;
  creator_name?: string | null;
};

const message = useMessage();
const queryClient = useQueryClient();

const pagination = reactive<PaginationProps>({
  page: 1,
  pageSize: 20,
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

const modelsQuery = useQuery({
  queryKey: ["models", "list"],
  queryFn: listModels,
  refetchInterval: 5000,
});

const models = computed(() => modelsQuery.data.value ?? []);
const isLoading = computed(() => modelsQuery.isLoading.value);
const keyword = ref("");
const filteredModels = computed<ModelRow[]>(() => {
  const query = keyword.value.trim().toLowerCase();
  const rows = models.value as ModelRow[];
  if (!query) return rows;
  return rows.filter((model) =>
    [
      modelDisplayName(model),
      modelCreatorName(model),
      model.id,
      model.dataset_name,
      model.trainer_name,
      model.format,
      model.job_id,
      model.dataset_id,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase()
      .includes(query),
  );
});

watch(keyword, () => {
  pagination.page = 1;
});

const renameVisible = ref(false);
const renameTarget = ref<ModelResponse | null>(null);
const renameName = ref("");

const renameMutation = useMutation({
  mutationFn: ({ id, name }: { id: string; name: string }) => renameModel(id, name),
  onSuccess: () => {
    message.success("Model renamed");
    queryClient.invalidateQueries({ queryKey: ["models"] });
    resetRename();
  },
  onError: (error: Error) => {
    message.error(error.message || "Failed to rename model");
  },
});

const deleteMutation = useMutation({
  mutationFn: (id: string) => deleteModel(id),
  onSuccess: () => {
    message.success("Model deleted");
    queryClient.invalidateQueries({ queryKey: ["models"] });
  },
  onError: (error: Error) => {
    message.error(error.message || "Failed to delete model");
  },
});

function modelDisplayName(row: ModelResponse): string {
  return row.name?.trim() || row.id.slice(0, 8);
}

function modelCreatorName(row: ModelRow): string {
  return row.creator_name?.trim() || row.created_by?.trim() || "system";
}

function openRename(row: ModelRow): void {
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
  renameMutation.mutate({ id: target.id, name });
  return false;
}

const columns = computed<DataTableColumns<ModelRow>>(() => [
  {
    title: "Model Name",
    key: "name",
    sorter: "default",
    render: (row) =>
      h(
        NText,
        { style: "font-weight: 500" },
        { default: () => modelDisplayName(row) },
      ),
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
      new Date(left.created_at ?? 0).getTime() -
      new Date(right.created_at ?? 0).getTime(),
    render: (row) =>
      row.created_at ? new Date(row.created_at).toLocaleString() : "-",
  },
  {
    title: "Actions",
    key: "actions",
    width: 160,
    render: (row) =>
      h(
        NSpace,
        { size: 6, wrap: false },
        {
          default: () => [
            h(
              NButton,
              { size: "small", quaternary: true, onClick: () => openRename(row) },
              { default: () => "Rename" },
            ),
            h(
              NPopconfirm,
              {
                onPositiveClick: () => deleteMutation.mutate(row.id),
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
                        deleteMutation.variables.value === row.id,
                    },
                    { default: () => "Delete" },
                  ),
                default: () => `Delete model '${modelDisplayName(row)}'?`,
              },
            ),
          ],
        },
      ),
  },
]);
</script>

<style scoped>
.models-view {
  height: 100%;
}

.models-search {
  max-width: 320px;
}
</style>
