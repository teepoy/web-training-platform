import { computed, reactive, ref, toValue, watch, type MaybeRefOrGetter } from "vue";
import { refDebounced } from "@vueuse/core";
import type { DataTableSortState, PaginationProps } from "naive-ui";
import { useI18n } from "vue-i18n";
import {
  getListModelsApiV1ModelsGetQueryKey,
  useListModelCreatorsApiV1ModelsCreatorsGet,
  useListModelsApiV1ModelsGet,
} from "@/generated/orval/endpoints/api";
import type { ListModelsApiV1ModelsGetParams, ModelResponse } from "@/generated/orval/models";
import { useAuthStore } from "@/features/auth/application/store";
import { useOrgStore } from "@/features/auth/application/org";
import { orgScopedQueryKey } from "@/shared/api";
import { useCreatorScopeQuery } from "@/shared/composables/useCreatorScopeQuery";

export type ModelSourceType = "dataset" | "collection";

export interface UseModelSearchOptions {
  active: MaybeRefOrGetter<boolean>;
  compatibleViewIds?: MaybeRefOrGetter<string[]>;
  refetchInterval?: number | false;
  onResetSelection?: () => void;
}

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
  return "created_at";
}

export function useModelSearch(options: UseModelSearchOptions) {
  const { t } = useI18n();
  const authStore = useAuthStore();
  const orgStore = useOrgStore();
  const keyword = ref("");
  const debouncedKeyword = refDebounced(keyword, 250);
  const sourceType = ref<ModelSourceType | null>(null);
  const sorter = ref<DataTableSortState | null>({
    columnKey: "created_at",
    order: "descend",
    sorter: true,
  });
  const compatibleViewIds = computed(() => [...new Set(toValue(options.compatibleViewIds) ?? [])]);
  const {
    creatorScope,
    creatorId,
    isReady: creatorFilterReady,
  } = useCreatorScopeQuery(
    () => orgStore.currentOrgId,
    () => authStore.user?.id,
    { defaultScope: "all" },
  );
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
      options.onResetSelection?.();
    },
  });
  const params = computed<ListModelsApiV1ModelsGetParams>(() => ({
    offset: ((pagination.page ?? 1) - 1) * (pagination.pageSize ?? 20),
    limit: pagination.pageSize ?? 20,
    q: debouncedKeyword.value.trim() || undefined,
    creator_id: creatorId.value ?? undefined,
    source_type: sourceType.value ?? undefined,
    compatible_view_id:
      compatibleViewIds.value.length > 0 ? compatibleViewIds.value.join(",") : undefined,
    sort_by: modelSortField(sorter.value?.columnKey),
    sort_order: sorter.value?.order === "ascend" ? "asc" : "desc",
  }));
  const queryKey = computed(() =>
    orgScopedQueryKey(orgStore.currentOrgId, getListModelsApiV1ModelsGetQueryKey(params.value)),
  );
  const query = useListModelsApiV1ModelsGet(params, {
    query: {
      queryKey,
      enabled: computed(
        () => !!orgStore.currentOrgId && creatorFilterReady.value && toValue(options.active),
      ),
      refetchInterval: options.refetchInterval,
    },
  });
  const creatorsQuery = useListModelCreatorsApiV1ModelsCreatorsGet({
    query: {
      queryKey: computed(() => orgScopedQueryKey(orgStore.currentOrgId, ["models", "creators"])),
      enabled: computed(() => !!orgStore.currentOrgId && toValue(options.active)),
    },
  });
  const models = computed<ModelResponse[]>(() => query.data.value?.items ?? []);
  const total = computed(() => query.data.value?.total ?? 0);
  const tablePagination = computed(() =>
    total.value > (pagination.pageSize ?? 20) ? pagination : false,
  );
  const activeFilterCount = computed(
    () =>
      Number(keyword.value.trim().length > 0) +
      Number(sourceType.value !== null) +
      Number(creatorScope.value !== "all"),
  );
  const hasFilters = computed(() => activeFilterCount.value > 0);
  const emptyDescription = computed(() => {
    if (hasFilters.value) return t("models.noMatches");
    if (compatibleViewIds.value.length > 0) return t("models.noCompatible");
    return t("models.noModels");
  });

  watch(
    () => query.data.value?.total ?? 0,
    (nextTotal) => {
      pagination.itemCount = nextTotal;
    },
    { immediate: true },
  );
  watch([keyword, sourceType, creatorId, compatibleViewIds], () => {
    pagination.page = 1;
    options.onResetSelection?.();
  });
  watch(
    () => [pagination.page, orgStore.currentOrgId],
    () => options.onResetSelection?.(),
  );

  function clearFilters(): void {
    keyword.value = "";
    sourceType.value = null;
    creatorScope.value = "all";
  }

  function handleSorterChange(value: DataTableSortState | DataTableSortState[] | null): void {
    sorter.value = Array.isArray(value) ? (value[0] ?? null) : value;
    pagination.page = 1;
    options.onResetSelection?.();
  }

  return {
    activeFilterCount,
    clearFilters,
    compatibleViewIds,
    creatorFilterReady,
    creators: computed(() => creatorsQuery.data.value ?? []),
    creatorsLoading: computed(() => creatorsQuery.isLoading.value),
    creatorScope,
    emptyDescription,
    error: computed(() => (query.error.value as Error | null) ?? null),
    handleSorterChange,
    isLoading: computed(
      () => !creatorFilterReady.value || query.isLoading.value || query.isFetching.value,
    ),
    keyword,
    models,
    pagination,
    params,
    query,
    sorter,
    sourceType,
    tablePagination,
    total,
  };
}
