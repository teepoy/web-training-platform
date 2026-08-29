<script setup lang="ts">
import { computed, h, ref, useSlots, watch } from "vue";
import type { DataTableColumns, DataTableRowKey } from "naive-ui";
import { NAlert, NButton, NDataTable, NEmpty, NText } from "naive-ui";
import { useGetModelApiV1ModelsModelIdGet } from "@/generated/orval/endpoints/api";
import type { ModelResponse } from "@/generated/orval/models";
import { useAuthStore } from "@/features/auth/application/store";
import { useOrgStore } from "@/features/auth/application/org";
import { orgScopedQueryKey } from "@/shared/api";
import ModelSearchFilters from "./ModelSearchFilters.vue";
import { useModelSearch } from "../composables/useModelSearch";

const props = withDefaults(
  defineProps<{
    mode: "management" | "selection";
    active?: boolean;
    compatibleViewIds?: string[];
    modelValue?: string | null;
    checkedRowKeys?: DataTableRowKey[];
    refetchInterval?: number | false;
    maxHeight?: number;
  }>(),
  {
    active: true,
    compatibleViewIds: () => [],
    modelValue: null,
    checkedRowKeys: () => [],
    refetchInterval: false,
    maxHeight: undefined,
  },
);

const emit = defineEmits<{
  (event: "update:modelValue", value: string | null): void;
  (event: "update:selectedModel", value: ModelResponse | null): void;
  (event: "update:checkedRowKeys", value: DataTableRowKey[]): void;
  (event: "openSource", value: ModelResponse): void;
}>();

const slots = useSlots();
const authStore = useAuthStore();
const orgStore = useOrgStore();
const selectedRecord = ref<ModelResponse | null>(null);
const search = useModelSearch({
  active: () => props.active,
  compatibleViewIds: () => props.compatibleViewIds,
  refetchInterval: props.refetchInterval,
  onResetSelection: () => {
    if (props.mode === "management") emit("update:checkedRowKeys", []);
  },
});

const selectedModelQuery = useGetModelApiV1ModelsModelIdGet(
  computed(() => props.modelValue ?? ""),
  {
    query: {
      queryKey: computed(() =>
        orgScopedQueryKey(orgStore.currentOrgId, ["models", "selected", props.modelValue]),
      ),
      enabled: computed(
        () =>
          props.mode === "selection" &&
          props.active &&
          !!orgStore.currentOrgId &&
          !!props.modelValue &&
          !search.models.value.some((model) => model.id === props.modelValue),
      ),
    },
  },
);
const selectedModel = computed(
  () =>
    search.models.value.find((model) => model.id === props.modelValue) ??
    (selectedRecord.value?.id === props.modelValue ? selectedRecord.value : null) ??
    selectedModelQuery.data.value ??
    null,
);
const checkedKeys = computed<DataTableRowKey[]>(() =>
  props.mode === "selection" ? (props.modelValue ? [props.modelValue] : []) : props.checkedRowKeys,
);
const selectedModels = computed(() => {
  const selectedIds = new Set(props.checkedRowKeys.map(String));
  return search.models.value.filter((model) => selectedIds.has(model.id));
});

watch(selectedModel, (model) => emit("update:selectedModel", model), { immediate: true });
watch(
  () => props.modelValue,
  (modelId) => {
    if (!modelId) selectedRecord.value = null;
  },
);

function modelDisplayName(model: ModelResponse): string {
  return model.name?.trim() || model.id.slice(0, 8);
}

function modelCreatorName(model: ModelResponse): string {
  return model.creator_name?.trim() || model.created_by?.trim() || "system";
}

function modelSourceName(model: ModelResponse): string {
  if (model.dataset_id) return model.dataset_name?.trim() || model.dataset_id.slice(0, 8);
  if (model.collection_id) {
    return model.collection_name?.trim() || model.collection_id.slice(0, 8);
  }
  return "—";
}

function sourceLabel(model: ModelResponse): string {
  if (model.dataset_id) return `Dataset · ${modelSourceName(model)}`;
  if (model.collection_id) return `Collection · ${modelSourceName(model)}`;
  return modelSourceName(model);
}

function selectRows(keys: DataTableRowKey[]): void {
  if (props.mode === "management") {
    emit("update:checkedRowKeys", keys);
    return;
  }
  const modelId = keys.length > 0 ? String(keys[keys.length - 1]) : null;
  selectedRecord.value = search.models.value.find((model) => model.id === modelId) ?? null;
  emit("update:modelValue", modelId);
}

function rowProps(model: ModelResponse): Record<string, unknown> {
  if (props.mode !== "selection") return {};
  return {
    style: { cursor: "pointer" },
    onClick: () => {
      selectedRecord.value = model;
      emit("update:modelValue", model.id);
    },
  };
}

const columns = computed<DataTableColumns<ModelResponse>>(() => {
  const sortable = props.mode === "management";
  const result: DataTableColumns<ModelResponse> = [
    {
      type: "selection",
      multiple: props.mode === "management",
      width: 42,
      fixed: "left",
      disabled:
        props.mode === "management"
          ? (model) => model.created_by !== authStore.user?.id
          : undefined,
    },
    {
      title: "Model",
      key: "name",
      minWidth: 180,
      sorter: sortable,
      sortOrder: search.sorter.value?.columnKey === "name" ? search.sorter.value.order : false,
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
      sorter: sortable,
      sortOrder: search.sorter.value?.columnKey === "source" ? search.sorter.value.order : false,
      render: (model) =>
        props.mode === "management" && (model.dataset_id || model.collection_id)
          ? h(
              NButton,
              {
                text: true,
                type: "primary",
                size: "small",
                onClick: () => emit("openSource", model),
              },
              { default: () => sourceLabel(model) },
            )
          : h(
              NText,
              { ellipsis: { tooltip: true }, title: sourceLabel(model) },
              { default: () => sourceLabel(model) },
            ),
    },
    {
      title: "Trainer",
      key: "trainer",
      minWidth: 130,
      sorter: sortable,
      sortOrder: search.sorter.value?.columnKey === "trainer" ? search.sorter.value.order : false,
      render: (model) => model.trainer_name,
    },
    {
      title: "Creator",
      key: "creator",
      minWidth: 130,
      sorter: sortable,
      sortOrder: search.sorter.value?.columnKey === "creator" ? search.sorter.value.order : false,
      render: modelCreatorName,
    },
    {
      title: "Created",
      key: "created_at",
      width: 170,
      sorter: sortable,
      sortOrder:
        search.sorter.value?.columnKey === "created_at" ? search.sorter.value.order : false,
      render: (model) => (model.created_at ? new Date(model.created_at).toLocaleString() : "—"),
    },
  ];
  if (props.mode === "management" && slots["row-actions"]) {
    result.push({
      title: "Actions",
      key: "actions",
      width: 150,
      fixed: "right",
      render: (model) => slots["row-actions"]?.({ model }),
    });
  }
  return result;
});
</script>

<template>
  <div class="model-search-surface" :data-mode="mode" data-testid="model-search-surface">
    <NText v-if="compatibleViewIds.length > 0" depth="3">
      Only models compatible with the selected resource are shown.
    </NText>
    <ModelSearchFilters
      :keyword="search.keyword.value"
      :source-type="search.sourceType.value"
      :creator-scope="search.creatorScope.value"
      :creators="search.creators.value"
      :creators-loading="search.creatorsLoading.value"
      :active-filter-count="search.activeFilterCount.value"
      @update:keyword="search.keyword.value = $event"
      @update:source-type="search.sourceType.value = $event"
      @update:creator-scope="search.creatorScope.value = $event"
      @clear="search.clearFilters"
    />
    <NAlert v-if="search.error.value" type="error" :title="search.error.value.message" />
    <slot
      v-if="mode === 'management'"
      name="bulk-actions"
      :selected-models="selectedModels"
      :clear-selection="() => emit('update:checkedRowKeys', [])"
    />
    <NDataTable
      :columns="columns"
      :data="search.models.value"
      :loading="search.isLoading.value"
      :pagination="search.tablePagination.value"
      :row-key="(row: ModelResponse) => row.id"
      :checked-row-keys="checkedKeys"
      :row-props="rowProps"
      :scroll-x="mode === 'management' ? 980 : 820"
      :max-height="maxHeight"
      remote
      size="small"
      @update:checked-row-keys="selectRows"
      @update:sorter="search.handleSorterChange"
    >
      <template #empty>
        <NEmpty :description="search.emptyDescription.value" />
      </template>
    </NDataTable>
    <NText v-if="search.models.value.length > 0" class="mobile-table-hint" depth="3">
      Swipe sideways to see model details{{
        mode === "management" ? " and management actions" : ""
      }}.
    </NText>
  </div>
</template>

<style scoped>
.model-search-surface {
  display: grid;
  gap: 12px;
  width: 100%;
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

.mobile-table-hint {
  display: none;
}

@media (max-width: 640px) {
  .mobile-table-hint {
    display: block;
    font-size: 12px;
  }
}
</style>
