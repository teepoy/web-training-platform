import { computed, reactive, ref, toValue, watch, type MaybeRefOrGetter } from "vue";
import { refDebounced } from "@vueuse/core";
import type { DataTableSortState, PaginationProps } from "naive-ui";

export interface UseRemoteListStateOptions {
  keyword: MaybeRefOrGetter<string>;
  filters?: Array<MaybeRefOrGetter<unknown>>;
  total: MaybeRefOrGetter<number>;
  initialSorter: DataTableSortState;
  onResetSelection?: () => void;
}

export function useRemoteListState(options: UseRemoteListStateOptions) {
  const keyword = computed(() => toValue(options.keyword));
  const debouncedKeyword = refDebounced(keyword, 250);
  const sorter = ref<DataTableSortState | null>(options.initialSorter);
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
  const filterValues = computed(() => (options.filters ?? []).map((filter) => toValue(filter)));

  watch(
    () => toValue(options.total),
    (total) => {
      pagination.itemCount = total;
    },
    { immediate: true },
  );
  watch(
    () => [keyword.value, ...filterValues.value],
    () => {
      pagination.page = 1;
      options.onResetSelection?.();
    },
  );
  watch(
    () => [pagination.page, pagination.pageSize],
    () => options.onResetSelection?.(),
  );

  function handleSorterChange(value: DataTableSortState | DataTableSortState[] | null): void {
    sorter.value = Array.isArray(value) ? (value[0] ?? null) : value;
    pagination.page = 1;
    options.onResetSelection?.();
  }

  return {
    debouncedKeyword,
    handleSorterChange,
    pagination,
    sorter,
    tablePagination: computed(() =>
      toValue(options.total) > (pagination.pageSize ?? 20) ? pagination : false,
    ),
  };
}
