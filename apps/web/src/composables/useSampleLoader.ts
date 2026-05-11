/**
 * useSampleLoader — paginated sample fetching composable.
 *
 * Provides an infinite-scroll-friendly API: call `loadMore()` to fetch the
 * next page; the composable merges pages into a single reactive array.
 *
 * Supports optional label filter, sort order, and an optional `sampleIds`
 * scope. When `sampleIds` is non-empty the loader switches from the default
 * paginated samples-with-labels path to the POST `/datasets/{id}/query`
 * sample-slice path so callers (e.g. a wafer-map brush) can render samples
 * that live outside the currently loaded page. When `sampleIds` is null or
 * empty the default pagination behaviour is preserved.
 */

import { ref, computed, type Ref, watch, isRef } from 'vue'
import { fetchSampleSlice, listSamplesWithLabels, type PaginatedResponse, type SampleWithLabels } from '@platform/web-data/samples'

export interface UseSampleLoaderOptions {
  datasetId: string | Ref<string>
  pageSize?: number
  labelFilter?: Ref<string | null>
  orderBy?: Ref<string>
  sampleIds?: Ref<string[] | null>
}

export function useSampleLoader(options: UseSampleLoaderOptions) {
  const resolvedId = isRef(options.datasetId) ? options.datasetId : ref(options.datasetId)
  const pageSize = options.pageSize ?? 100

  const samples = ref<SampleWithLabels[]>([])
  const totalCount = ref(0)
  const isLoading = ref(false)
  const initialized = ref(false)

  const hasMore = computed(() => !initialized.value || samples.value.length < totalCount.value)

  function activeSampleIds(): string[] | null {
    const ids = options.sampleIds?.value
    return ids && ids.length > 0 ? ids : null
  }

  async function fetchPage(offset: number): Promise<PaginatedResponse<SampleWithLabels>> {
    const ids = activeSampleIds()
    if (ids) {
      return fetchSampleSlice(resolvedId.value, {
        offset,
        limit: pageSize,
        label: options.labelFilter?.value ?? null,
        orderBy: options.orderBy?.value ?? 'id',
        sampleIds: ids,
      })
    }
    return listSamplesWithLabels(
      resolvedId.value,
      offset,
      pageSize,
      options.labelFilter?.value ?? undefined,
      options.orderBy?.value ?? 'id',
    )
  }

  async function loadMore() {
    if (!resolvedId.value) return
    if (initialized.value && !hasMore.value) return
    if (isLoading.value) return

    isLoading.value = true
    try {
      const result = await fetchPage(samples.value.length)
      totalCount.value = result.total
      samples.value = [...samples.value, ...result.items]
      initialized.value = true
    } finally {
      isLoading.value = false
    }
  }

  function reset() {
    samples.value = []
    totalCount.value = 0
    initialized.value = false
    void loadMore()
  }

  if (options.labelFilter) {
    watch(options.labelFilter, () => reset())
  }
  if (options.orderBy) {
    watch(options.orderBy, () => reset())
  }
  if (options.sampleIds) {
    watch(
      () => options.sampleIds?.value ?? null,
      (next, prev) => {
        const a = (next ?? []).join(',')
        const b = (prev ?? []).join(',')
        if (a !== b) reset()
      },
    )
  }

  if (isRef(options.datasetId)) {
    watch(options.datasetId, (newId) => {
      if (newId) reset()
    })
  }

  return {
    samples,
    totalCount,
    isLoading,
    hasMore,
    loadMore,
    reset,
  }
}
