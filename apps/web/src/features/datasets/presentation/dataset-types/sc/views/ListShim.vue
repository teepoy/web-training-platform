<template>
  <div data-testid="datasets-shim-sc">
    <DatasetToolbar title="Patch Datasets" />

    <div class="sc-dataset-list-filters">
      <n-input
        v-model:value="keyword"
        size="small"
        clearable
        placeholder="Search datasets"
        class="sc-dataset-list-search"
      />
      <n-select
        v-model:value="creatorFilter"
        size="small"
        clearable
        placeholder="Creator"
        :options="creatorOptions"
        class="sc-dataset-list-creator"
      />
    </div>

    <n-data-table
      :columns="columns"
      :data="filteredDatasets"
      :row-key="(row: DatasetListItem) => row.id"
      :bordered="false"
      size="small"
      :pagination="pagination"
      @update:checked-row-keys="handleCheckedRowKeysChange"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, h, reactive, ref, watch } from "vue";
import type { DataTableColumns, PaginationProps } from "naive-ui";
import {
  NButton,
  NDataTable,
  NInput,
  NSelect,
  NTag,
  NText,
  NSpace,
} from "naive-ui";
import { DatasetToolbar } from "@/shared";
import type { DatasetListItem } from "@/shared/datasets/types";

const props = withDefaults(
  defineProps<{
    datasets: DatasetListItem[];
    currentOrgId: string | null;
    currentUserId?: string | null;
    isSuperadmin: boolean;
  }>(),
  {
    currentUserId: null,
  },
);

const emit = defineEmits<{
  view: [id: string];
  "toggle-public": [payload: { id: string; isPublic: boolean }];
  delete: [row: DatasetListItem];
}>();

function handleCheckedRowKeysChange(_keys: (string | number)[]) {
  // Reserved for batch operations
}

function toDisplayCount(value: unknown): string | null {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "string" && value.trim() !== "") return value;
  return null;
}

function resolveSampleCount(row: DatasetListItem): string {
  const meta = row.dataset_meta ?? {};
  return (
    toDisplayCount(meta.sample_count) ??
    toDisplayCount(meta.total_samples) ??
    toDisplayCount(meta.samples_count) ??
    toDisplayCount(meta.total_rows) ??
    "0"
  );
}

function resolveCreator(row: DatasetListItem): string {
  return row.creator_name?.trim() || row.created_by?.trim() || "system";
}

function formatCreateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

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

const keyword = ref("");
const creatorFilter = ref<string | null>(null);

const creatorOptions = computed(() =>
  Array.from(new Set(props.datasets.map(resolveCreator)))
    .sort((left, right) =>
      left.localeCompare(right, undefined, { numeric: true }),
    )
    .map((creator) => ({ label: creator, value: creator })),
);

watch([keyword, creatorFilter], () => {
  pagination.page = 1;
});

const filteredDatasets = computed(() => {
  const query = keyword.value.trim().toLowerCase();
  const creator = creatorFilter.value;
  return props.datasets.filter((row) => {
    if (creator && resolveCreator(row) !== creator) return false;
    if (!query) return true;
    const searchable = [
      row.name,
      row.id,
      row.dataset_type,
      resolveCreator(row),
      resolveSampleCount(row),
      row.created_at,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return searchable.includes(query);
  });
});

const columns = computed<DataTableColumns<DatasetListItem>>(
  () => [
    {
      title: "Name",
      key: "name",
      width: 220,
      sorter: "default",
      filterOptionValue: null,
      filterOptions: Array.from(new Set(props.datasets.map((row) => row.name)))
        .sort((left, right) =>
          left.localeCompare(right, undefined, { numeric: true }),
        )
        .map((name) => ({
          label: name,
          value: name,
        })),
      filter(value, row) {
        return row.name === value;
      },
      render(row) {
        return h(
          NText,
          { style: "font-weight: 500" },
          { default: () => row.name },
        );
      },
    },
    {
      title: "Task Type",
      key: "task_type",
      width: 150,
      render() {
        return h(
          NTag,
          { type: "info", size: "small", bordered: false },
          { default: () => "Patch" },
        );
      },
    },
    {
      title: "Samples",
      key: "sample_count",
      width: 100,
      sorter: (left, right) =>
        Number(resolveSampleCount(left)) - Number(resolveSampleCount(right)),
      render(row) {
        return h(NText, {}, { default: () => resolveSampleCount(row) });
      },
    },
    {
      title: "Creator",
      key: "created_by",
      width: 160,
      sorter: "default",
      filterOptions: creatorOptions.value,
      filter(value, row) {
        return resolveCreator(row) === value;
      },
      render(row) {
        return h(NText, {}, { default: () => resolveCreator(row) });
      },
    },
    {
      title: "Create Time",
      key: "created_at",
      width: 180,
      sorter: (left, right) =>
        new Date(left.created_at).getTime() -
        new Date(right.created_at).getTime(),
      render(row) {
        return h(NText, {}, { default: () => formatCreateTime(row.created_at) });
      },
    },
    {
      title: "Actions",
      key: "actions",
      width: 150,
      render(row) {
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
                  onClick: () => emit("view", row.id),
                },
                { default: () => "View" },
              ),
              row.created_by === props.currentUserId
                ? h(
                    NButton,
                    {
                      size: "small",
                      quaternary: true,
                      type: "error",
                      onClick: () => emit("delete", row),
                    },
                    { default: () => "Delete" },
                  )
                : null,
            ],
          },
        );
      },
    },
  ],
);
</script>

<style scoped>
.sc-dataset-list-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin: 8px 0 12px;
}

.sc-dataset-list-search {
  width: min(280px, 100%);
}

.sc-dataset-list-creator {
  width: min(180px, 100%);
}
</style>
