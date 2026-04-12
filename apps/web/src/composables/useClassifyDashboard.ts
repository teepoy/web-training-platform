/**
 * useClassifyDashboard — data layer for the classify sidebar.
 *
 * Fetches server-side annotation stats and merges them with transient local
 * state (draft count, selection count) so widgets receive a single normalised
 * data object.
 */

import { computed, isRef, ref, type Ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { api } from '../api'
import type { DatasetAnnotationStats } from '../types'

// ---------------------------------------------------------------------------
// Merged context that widgets receive
// ---------------------------------------------------------------------------

export interface ClassifyDashboardContext {
  /** Server-side annotation stats (null while loading or on error). */
  stats: DatasetAnnotationStats | null
  /** Whether the stats query is currently loading. */
  isLoading: boolean
  /** Whether the stats query encountered an error. */
  isError: boolean
  /** Error message when the stats query fails. */
  errorMessage: string | null
  /** Number of samples with a pending local draft label. */
  draftCount: number
  /** Number of currently selected sample rows. */
  selectedCount: number
  /** Dataset label space (from the dataset query). */
  labelSpace: string[]
  /** Refetch stats from the server. */
  refetch: () => void
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useClassifyDashboard(
  datasetId: string | Ref<string>,
  draftCount: Ref<number>,
  selectedCount: Ref<number>,
  labelSpace: Ref<string[]>,
): ClassifyDashboardContext {
  const resolvedId = isRef(datasetId) ? datasetId : ref(datasetId)

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: computed(() => ['annotation-stats', resolvedId.value]),
    queryFn: () => api.getAnnotationStats(resolvedId.value),
    enabled: computed(() => resolvedId.value !== ''),
    refetchInterval: 15_000,
    retry: 1,
  })

  const stats = computed<DatasetAnnotationStats | null>(() => data.value ?? null)
  const errorMessage = computed<string | null>(() => {
    if (!isError.value) return null
    const e = error.value
    if (e instanceof Error) return e.message
    return String(e ?? 'Unknown error')
  })

  return {
    get stats() { return stats.value },
    get isLoading() { return isLoading.value },
    get isError() { return isError.value },
    get errorMessage() { return errorMessage.value },
    get draftCount() { return draftCount.value },
    get selectedCount() { return selectedCount.value },
    get labelSpace() { return labelSpace.value },
    refetch,
  }
}
