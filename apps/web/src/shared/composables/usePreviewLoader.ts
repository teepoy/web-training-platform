import { ref, computed, type Ref } from "vue";
import { useInfiniteQuery } from "@tanstack/vue-query";
import { listPreviewItems, type PreviewItem } from "../api/preview";

export interface UsePreviewLoaderOptions {
  sessionId: string | Ref<string>;
  pageSize?: number;
}

export function usePreviewLoader(options: UsePreviewLoaderOptions) {
  const resolvedId =
    typeof options.sessionId === "string"
      ? ref(options.sessionId)
      : options.sessionId;
  const pageSize = options.pageSize ?? 20;

  const infiniteQuery = useInfiniteQuery({
    queryKey: computed(() => ["preview-items", resolvedId.value]),
    queryFn: ({ pageParam }: { pageParam: string | null }) =>
      listPreviewItems(resolvedId.value, pageParam, pageSize),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: false,
  });

  const items = computed(() => {
    const all = (infiniteQuery.data.value?.pages ?? []).flatMap(
      (p) => p.items,
    );
    const seen = new Set<string>();
    return all.filter((item: PreviewItem) => {
      if (seen.has(item.upstream_item_id)) return false;
      seen.add(item.upstream_item_id);
      return true;
    });
  });

  const estimatedTotal = computed(
    () =>
      infiniteQuery.data.value?.pages?.[
        infiniteQuery.data.value.pages.length - 1
      ]?.estimated_total ?? null,
  );

  const loadedCount = computed(() => items.value.length);

  const isLoading = computed(
    () =>
      infiniteQuery.isFetching.value ||
      infiniteQuery.isFetchingNextPage.value,
  );

  const hasMore = computed(
    () => infiniteQuery.hasNextPage.value ?? true,
  );

  const initialized = computed(
    () => infiniteQuery.data.value !== undefined,
  );

  async function loadMore() {
    if (
      infiniteQuery.isFetching.value ||
      infiniteQuery.isFetchingNextPage.value
    )
      return;

    if (infiniteQuery.data.value === undefined) {
      await infiniteQuery.refetch();
      return;
    }

    if (!infiniteQuery.hasNextPage.value) return;
    await infiniteQuery.fetchNextPage();
  }

  function reset() {
    infiniteQuery.refetch();
  }

  return {
    items,
    estimatedTotal,
    loadedCount,
    isLoading,
    hasMore,
    initialized,
    loadMore,
    reset,
  };
}
