<script setup lang="ts">
import { computed, h, reactive, ref, watch } from "vue";
import { refDebounced } from "@vueuse/core";
import type { DataTableColumns, DataTableRowKey, PaginationProps, SelectOption } from "naive-ui";
import { NButton, NDataTable, NEmpty, NInput, NSelect, NText } from "naive-ui";
import {
  useGetModelApiV1ModelsModelIdGet,
  useListModelCreatorsApiV1ModelsCreatorsGet,
  useListModelsApiV1ModelsGet,
} from "@/generated/orval/endpoints/api";
import type { ListModelsApiV1ModelsGetParams, ModelResponse } from "@/generated/orval/models";
import { useAuthStore } from "@/features/auth/application/store";
import { useOrgStore } from "@/features/auth/application/org";
import { orgScopedQueryKey } from "@/shared/api";
import CreatorScopeSelect from "@/shared/components/creator-scope-select";

const props = withDefaults(
  defineProps<{
    modelValue: string | null;
    active: boolean;
    compatibleViewIds?: string[];
  }>(),
  { compatibleViewIds: () => [] },
);

const emit = defineEmits<{
  (event: "update:modelValue", value: string | null): void;
  (event: "update:selectedModel", value: ModelResponse | null): void;
}>();

const authStore = useAuthStore();
const orgStore = useOrgStore();
const search = ref("");
const debouncedSearch = refDebounced(search, 250);
const sourceType = ref<"dataset" | "collection" | null>(null);
const creatorScope = ref("all");
const selectedRecord = ref<ModelResponse | null>(null);
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

const creatorId = computed(() => {
  if (creatorScope.value === "all") return undefined;
  if (creatorScope.value === "me") return authStore.user?.id;
  return creatorScope.value;
});

const params = computed<ListModelsApiV1ModelsGetParams>(() => ({
  offset: ((pagination.page ?? 1) - 1) * (pagination.pageSize ?? 20),
  limit: pagination.pageSize ?? 20,
  q: debouncedSearch.value.trim() || undefined,
  source_type: sourceType.value ?? undefined,
  creator_id: creatorId.value,
  compatible_view_id:
    props.compatibleViewIds.length > 0
      ? [...new Set(props.compatibleViewIds)].join(",")
      : undefined,
  sort_by: "created_at",
  sort_order: "desc",
}));

const modelsQuery = useListModelsApiV1ModelsGet(params, {
  query: {
    queryKey: computed(() =>
      orgScopedQueryKey(orgStore.currentOrgId, ["models", "remote-picker", params.value]),
    ),
    enabled: computed(() => !!orgStore.currentOrgId && props.active),
  },
});
const models = computed(() => modelsQuery.data.value?.items ?? []);

const selectedModelQuery = useGetModelApiV1ModelsModelIdGet(
  computed(() => props.modelValue ?? ""),
  {
    query: {
      queryKey: computed(() =>
        orgScopedQueryKey(orgStore.currentOrgId, ["models", "selected", props.modelValue]),
      ),
      enabled: computed(
        () =>
          !!orgStore.currentOrgId &&
          props.active &&
          !!props.modelValue &&
          !models.value.some((model) => model.id === props.modelValue),
      ),
    },
  },
);

const selectedModel = computed(
  () =>
    models.value.find((model) => model.id === props.modelValue) ??
    (selectedRecord.value?.id === props.modelValue ? selectedRecord.value : null) ??
    selectedModelQuery.data.value ??
    null,
);

watch(
  () => modelsQuery.data.value?.total ?? 0,
  (total) => {
    pagination.itemCount = total;
  },
  { immediate: true },
);
watch([debouncedSearch, sourceType, creatorScope, () => props.compatibleViewIds], () => {
  pagination.page = 1;
});
watch(selectedModel, (model) => emit("update:selectedModel", model), { immediate: true });
watch(
  () => props.modelValue,
  (modelId) => {
    if (!modelId) selectedRecord.value = null;
  },
);

const sourceOptions: SelectOption[] = [
  { label: "Dataset", value: "dataset" },
  { label: "Collection", value: "collection" },
];
const creatorsQuery = useListModelCreatorsApiV1ModelsCreatorsGet({
  query: {
    queryKey: computed(() => orgScopedQueryKey(orgStore.currentOrgId, ["models", "creators"])),
    enabled: computed(() => !!orgStore.currentOrgId && props.active),
  },
});

const filterCount = computed(
  () =>
    Number(search.value.trim().length > 0) +
    Number(sourceType.value !== null) +
    Number(creatorScope.value !== "all"),
);

function clearFilters(): void {
  search.value = "";
  sourceType.value = null;
  creatorScope.value = "all";
}

function modelDisplayName(model: ModelResponse): string {
  return model.name?.trim() || model.id.slice(0, 8);
}

function modelSourceName(model: ModelResponse): string {
  if (model.dataset_id) return `Dataset · ${model.dataset_name?.trim() || model.dataset_id}`;
  if (model.collection_id) {
    return `Collection · ${model.collection_name?.trim() || model.collection_id}`;
  }
  return "Unknown source";
}

function selectModel(keys: DataTableRowKey[]): void {
  const modelId = keys.length ? String(keys[keys.length - 1]) : null;
  selectedRecord.value = models.value.find((model) => model.id === modelId) ?? null;
  emit("update:modelValue", modelId);
}

function rowProps(model: ModelResponse): Record<string, unknown> {
  return {
    style: { cursor: "pointer" },
    onClick: () => {
      selectedRecord.value = model;
      emit("update:modelValue", model.id);
    },
  };
}

const columns = computed<DataTableColumns<ModelResponse>>(() => [
  { type: "selection", multiple: false, width: 42 },
  {
    title: "Model",
    key: "name",
    minWidth: 180,
    render: (model) =>
      h("div", {}, [
        h(
          NText,
          { strong: true, ellipsis: { tooltip: true }, style: { display: "block" } },
          { default: () => modelDisplayName(model) },
        ),
        h(NText, { depth: 3, title: model.id, class: "model-id" }, { default: () => model.id }),
      ]),
  },
  {
    title: "Training source",
    key: "source",
    minWidth: 190,
    render: (model) =>
      h(
        NText,
        { ellipsis: { tooltip: true }, title: modelSourceName(model) },
        { default: () => modelSourceName(model) },
      ),
  },
  { title: "Trainer", key: "trainer_name", minWidth: 130 },
  {
    title: "Creator",
    key: "creator_name",
    minWidth: 130,
    render: (model) => model.creator_name?.trim() || model.created_by,
  },
  {
    title: "Created",
    key: "created_at",
    width: 170,
    render: (model) => (model.created_at ? new Date(model.created_at).toLocaleString() : "—"),
  },
]);
</script>

<template>
  <div class="remote-model-picker" data-testid="remote-model-picker">
    <NText v-if="props.compatibleViewIds.length > 0" depth="3">
      Only models compatible with the selected resource are shown.
    </NText>
    <div class="model-picker-filters">
      <NInput v-model:value="search" clearable placeholder="Search models" />
      <NSelect
        v-model:value="sourceType"
        clearable
        :options="sourceOptions"
        placeholder="All training sources"
      />
      <CreatorScopeSelect
        v-model="creatorScope"
        :creators="creatorsQuery.data.value ?? []"
        :loading="creatorsQuery.isLoading.value"
        resource-label="models"
      />
      <NButton v-if="filterCount > 0" quaternary @click="clearFilters">
        Clear filters ({{ filterCount }})
      </NButton>
    </div>
    <NDataTable
      :columns="columns"
      :data="models"
      :loading="modelsQuery.isLoading.value"
      :pagination="pagination"
      :row-key="(row: ModelResponse) => row.id"
      :checked-row-keys="props.modelValue ? [props.modelValue] : []"
      :row-props="rowProps"
      :scroll-x="820"
      :max-height="320"
      remote
      size="small"
      @update:checked-row-keys="selectModel"
    >
      <template #empty>
        <NEmpty
          :description="
            props.compatibleViewIds.length > 0
              ? 'No compatible models match these filters'
              : 'No models match these filters'
          "
        />
      </template>
    </NDataTable>
  </div>
</template>

<style scoped>
.remote-model-picker {
  display: grid;
  gap: 12px;
  width: 100%;
}

.model-picker-filters {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) 180px 180px auto;
  gap: 8px;
}

.model-id {
  display: block;
  max-width: 190px;
  margin-top: 2px;
  overflow: hidden;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 760px) {
  .model-picker-filters {
    grid-template-columns: 1fr;
  }
}
</style>
