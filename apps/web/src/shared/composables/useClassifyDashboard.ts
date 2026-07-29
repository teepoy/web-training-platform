/**
 * useClassifyDashboard — data layer for the classify sidebar.
 *
 * Fetches server-side annotation stats and merges them with transient local
 * state (draft count, selection count) so widgets receive a single normalised
 * data object.
 */

import { computed, isRef, ref, type Ref } from "vue";
import {
  getGetAnnotationStatsApiV1DatasetsDatasetIdAnnotationStatsGetQueryKey,
  useGetAnnotationStatsApiV1DatasetsDatasetIdAnnotationStatsGet,
} from "@/generated/orval/endpoints/api";
import type { DatasetAnnotationStats } from "@/generated/orval/models";
import { useOrgStore } from "@/features/auth/application/org";
import { orgScopedQueryKey, toUserMessage } from "../api";
import type { ClassifyDashboardContext } from "../types/sidebar-widgets";

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useClassifyDashboard(
  datasetId: string | Ref<string>,
  draftCount: Ref<number>,
  selectedCount: Ref<number>,
  labelSpace: Ref<string[]>,
): ClassifyDashboardContext {
  const resolvedId = isRef(datasetId) ? datasetId : ref(datasetId);
  const orgStore = useOrgStore();

  const { data, isLoading, isError, error, refetch } =
    useGetAnnotationStatsApiV1DatasetsDatasetIdAnnotationStatsGet(resolvedId, {
      query: {
        queryKey: computed(() =>
          orgScopedQueryKey(
            orgStore.currentOrgId,
            getGetAnnotationStatsApiV1DatasetsDatasetIdAnnotationStatsGetQueryKey(resolvedId.value),
          ),
        ),
        enabled: computed(() => !!orgStore.currentOrgId && resolvedId.value !== ""),
        refetchInterval: 15_000,
        retry: 1,
      },
    });

  const stats = computed<DatasetAnnotationStats | null>(() => data.value ?? null);
  const errorMessage = computed<string | null>(() => {
    if (!isError.value) return null;
    return toUserMessage(error.value, "Failed to load annotation statistics");
  });

  return {
    get stats() {
      return stats.value;
    },
    get isLoading() {
      return isLoading.value;
    },
    get isError() {
      return isError.value;
    },
    get errorMessage() {
      return errorMessage.value;
    },
    get draftCount() {
      return draftCount.value;
    },
    get selectedCount() {
      return selectedCount.value;
    },
    get labelSpace() {
      return labelSpace.value;
    },
    refetch,
  };
}
