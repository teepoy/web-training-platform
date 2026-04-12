/**
 * useSampleLoader — paginated sample fetching composable.
 *
 * Provides an infinite-scroll–friendly API: call `loadMore()` to fetch the
 * next page; the composable merges pages into a single reactive array.
 *
 * Supports optional label filter and sort order.  Call `reset()` to start
 * over from page 0 (e.g. when filters change).
 */

import { ref, computed, type Ref, watch, isRef } from 'vue'
import { listSamplesWithLabels } from '../api'
import type { SampleWithLabels } from '../types'

export interface UseSampleLoaderOptions {
  datasetId: string | Ref<string>
  pageSize?: number
  labelFilter?: Ref<string | null>
  orderBy?: Ref<string>
}

export function useSampleLoader(options: UseSampleLoaderOptions) {
  const resolvedId = isRef(options.datasetId) ? options.datasetId : ref(options.datasetId)
  const pageSize = options.pageSize ?? 100

  const samples = ref<SampleWithLabels[]>([])
  const totalCount = ref(0)
  const isLoading = ref(false)
  const initialized = ref(false)

  const hasMore = computed(() => !initialized.value || samples.value.length < totalCount.value)

  async function loadMore() {
    if (!resolvedId.value) return
    if (initialized.value && !hasMore.value) return
    if (isLoading.value) return

    isLoading.value = true
    try {
      const result = await listSamplesWithLabels(
        resolvedId.value,
        samples.value.length,
        pageSize,
        options.labelFilter?.value ?? undefined,
        options.orderBy?.value ?? 'id',
      )
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

  // Re-fetch when filters change
  if (options.labelFilter) {
    watch(options.labelFilter, () => reset())
  }
  if (options.orderBy) {
    watch(options.orderBy, () => reset())
  }

  // Re-fetch when datasetId changes (for Ref<string> case)
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
