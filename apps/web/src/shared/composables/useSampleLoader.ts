/**
 * useSampleLoader — paginated sample fetching composable.
 *
 * Provides an infinite-scroll-friendly API backed by TanStack useInfiniteQuery.
 * Call `loadMore()` to fetch the next page; the composable merges pages into a
 * single reactive array. Query key changes (datasetId, labelFilter, orderBy,
 * sampleIds) automatically reset and refetch.
 *
 * Supports optional label filter, sort order, and an optional `sampleIds`
 * scope. When `sampleIds` is non-empty the loader switches from the default
 * paginated samples-with-labels path to the POST `/datasets/{id}/query`
 * sample-slice path.
 */

import { ref, computed, type Ref, isRef } from "vue";
import { useInfiniteQuery } from "@tanstack/vue-query";
import { getActivePinia } from "pinia";
import { fetchSampleSlice } from "../api/datasets";
import { listSamplesWithLabelsEndpointApiV1DatasetsDatasetIdSamplesWithLabelsGet } from "@/generated/orval/endpoints/api";
import { useOrgStore } from "@/features/auth/application/org";
import { orgScopedQueryKey } from "../api";
import type { PaginatedResponse } from "../api/types";
import type { SampleWithLabels } from "@/generated/orval/models";

export interface UseSampleLoaderOptions {
  datasetId: string | Ref<string>;
  pageSize?: number;
  labelFilter?: Ref<string | null>;
  orderBy?: Ref<string>;
  sampleIds?: Ref<string[] | null>;
}

export function useSampleLoader(options: UseSampleLoaderOptions) {
  const activePinia = getActivePinia();
  const orgStore = activePinia ? useOrgStore(activePinia) : null;
  const resolvedId = isRef(options.datasetId) ? options.datasetId : ref(options.datasetId);
  const pageSize = options.pageSize ?? 100;

  const queryKey = computed(() =>
    orgScopedQueryKey(orgStore?.currentOrgId, [
      "sample-loader",
      resolvedId.value,
      options.labelFilter?.value ?? null,
      options.orderBy?.value ?? "id",
      (options.sampleIds?.value ?? []).join(","),
    ]),
  );

  const infiniteQuery = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam }: { pageParam: number }) => {
      const ids = options.sampleIds?.value;
      if (ids && ids.length > 0) {
        return fetchSampleSlice(resolvedId.value, {
          offset: pageParam,
          limit: pageSize,
          label: options.labelFilter?.value ?? null,
          orderBy: options.orderBy?.value ?? "id",
          sampleIds: ids,
        });
      }
      return listSamplesWithLabelsEndpointApiV1DatasetsDatasetIdSamplesWithLabelsGet(
        resolvedId.value,
        {
          offset: pageParam,
          limit: pageSize,
          label: options.labelFilter?.value ?? undefined,
          order_by: options.orderBy?.value ?? "id",
        },
      );
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      const last = lastPage as PaginatedResponse<SampleWithLabels>;
      const loadedCount = allPages.reduce(
        (sum: number, p) => sum + (p as PaginatedResponse<SampleWithLabels>).items.length,
        0,
      );
      return loadedCount < last.total ? loadedCount : undefined;
    },
    enabled: computed(() => !!resolvedId.value),
  });

  const samples = computed(() =>
    (infiniteQuery.data.value?.pages ?? []).flatMap(
      (p) => (p as PaginatedResponse<SampleWithLabels>).items,
    ),
  );

  const totalCount = computed(() => {
    const pages = infiniteQuery.data.value?.pages as
      | PaginatedResponse<SampleWithLabels>[]
      | undefined;
    return pages && pages.length > 0 ? pages[pages.length - 1].total : 0;
  });

  const isLoading = computed(
    () => infiniteQuery.isFetching.value || infiniteQuery.isFetchingNextPage.value,
  );

  const hasMore = computed(() => infiniteQuery.hasNextPage.value ?? false);

  async function loadMore() {
    if (infiniteQuery.isFetchingNextPage.value || infiniteQuery.isFetching.value) return;

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
    samples,
    totalCount,
    isLoading,
    hasMore,
    loadMore,
    reset,
  };
}
