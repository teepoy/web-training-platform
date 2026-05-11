import { useQuery } from "@tanstack/vue-query";
import { computed } from "vue";
import { queryWaferPoints } from "./api";
import { agentKeys } from "./keys";

export function useWaferPointsQuery(datasetId: () => string) {
  return useQuery({
    queryKey: computed(() => agentKeys.query(datasetId(), "wafer-points")),
    queryFn: () => queryWaferPoints(datasetId()),
    enabled: computed(() => !!datasetId()),
  });
}
