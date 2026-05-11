import { useQuery, useMutation } from "@tanstack/vue-query";
import { computed } from "vue";
import { listDatasets, getDataset, getAnnotationStats, deleteDataset } from "./api";
import { datasetKeys } from "./keys";

export function useDatasetsQuery(orgId: () => string | null) {
  return useQuery({
    queryKey: computed(() => datasetKeys.list(orgId())),
    queryFn: () => listDatasets(),
    enabled: computed(() => !!orgId()),
  });
}

export function useDatasetQuery(id: () => string) {
  return useQuery({
    queryKey: computed(() => datasetKeys.detail(id())),
    queryFn: ({ queryKey }) => getDataset(queryKey[2] as string),
    enabled: computed(() => !!id()),
  });
}

export function useAnnotationStatsQuery(datasetId: () => string) {
  return useQuery({
    queryKey: computed(() => datasetKeys.annotationStats(datasetId())),
    queryFn: ({ queryKey }) => getAnnotationStats(queryKey[2] as string),
    enabled: computed(() => !!datasetId()),
    refetchInterval: 15_000,
    retry: 1,
  });
}

export function useDeleteDatasetMutation() {
  return useMutation({
    mutationFn: (id: string) => deleteDataset(id),
  });
}
