import { computed, isRef, ref, watch, type Ref } from "vue";
import { useQuery } from "@tanstack/vue-query";
import {
  fetchSampleSlice,
  getAnnotationStats,
  listSamplesWithLabels,
} from "@/modules/datasets/api";
import type { PaginatedResponse, SampleWithLabels } from "@/modules/datasets/types";
import type { ClassifyDashboardContext } from "./types";

export interface UseSampleLoaderOptions {
  datasetId: string | Ref<string>;
  pageSize?: number;
  labelFilter?: Ref<string | null>;
  orderBy?: Ref<string>;
  sampleIds?: Ref<string[] | null>;
}

export function useClassifyDashboard(
  datasetId: string | Ref<string>,
  draftCount: Ref<number>,
  selectedCount: Ref<number>,
  labelSpace: Ref<string[]>,
): ClassifyDashboardContext {
  const resolvedId = isRef(datasetId) ? datasetId : ref(datasetId);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: computed(() => ["annotation-stats", resolvedId.value]),
    queryFn: () => getAnnotationStats(resolvedId.value),
    enabled: computed(() => resolvedId.value !== ""),
    refetchInterval: 15_000,
    retry: 1,
  });

  const stats = computed(() => data.value ?? null);
  const errorMessage = computed<string | null>(() => {
    if (!isError.value) return null;
    const e = error.value;
    if (e instanceof Error) return e.message;
    return String(e ?? "Unknown error");
  });

  return {
    get stats() { return stats.value; },
    get isLoading() { return isLoading.value; },
    get isError() { return isError.value; },
    get errorMessage() { return errorMessage.value; },
    get draftCount() { return draftCount.value; },
    get selectedCount() { return selectedCount.value; },
    get labelSpace() { return labelSpace.value; },
    refetch,
  };
}

export function useSampleLoader(options: UseSampleLoaderOptions) {
  const resolvedId = isRef(options.datasetId) ? options.datasetId : ref(options.datasetId);
  const pageSize = options.pageSize ?? 100;

  const samples = ref<SampleWithLabels[]>([]);
  const totalCount = ref(0);
  const isLoading = ref(false);
  const initialized = ref(false);

  const hasMore = computed(() => !initialized.value || samples.value.length < totalCount.value);

  function activeSampleIds(): string[] | null {
    const ids = options.sampleIds?.value;
    return ids && ids.length > 0 ? ids : null;
  }

  async function fetchPage(offset: number): Promise<PaginatedResponse<SampleWithLabels>> {
    const ids = activeSampleIds();
    if (ids) {
      return fetchSampleSlice(resolvedId.value, {
        offset,
        limit: pageSize,
        label: options.labelFilter?.value ?? null,
        orderBy: options.orderBy?.value ?? "id",
        sampleIds: ids,
      });
    }
    return listSamplesWithLabels(
      resolvedId.value,
      offset,
      pageSize,
      options.labelFilter?.value ?? undefined,
      options.orderBy?.value ?? "id",
    );
  }

  async function loadMore() {
    if (!resolvedId.value) return;
    if (initialized.value && !hasMore.value) return;
    if (isLoading.value) return;

    isLoading.value = true;
    try {
      const result = await fetchPage(samples.value.length);
      totalCount.value = result.total;
      samples.value = [...samples.value, ...result.items];
      initialized.value = true;
    } finally {
      isLoading.value = false;
    }
  }

  function reset() {
    samples.value = [];
    totalCount.value = 0;
    initialized.value = false;
    void loadMore();
  }

  if (options.labelFilter) {
    watch(options.labelFilter, () => reset());
  }
  if (options.orderBy) {
    watch(options.orderBy, () => reset());
  }
  if (options.sampleIds) {
    watch(
      () => options.sampleIds?.value ?? null,
      (next, prev) => {
        const a = (next ?? []).join(",");
        const b = (prev ?? []).join(",");
        if (a !== b) reset();
      },
    );
  }

  if (isRef(options.datasetId)) {
    watch(options.datasetId, (newId) => {
      if (newId) reset();
    });
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
