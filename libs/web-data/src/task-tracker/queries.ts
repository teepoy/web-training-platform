import { useQuery, useMutation } from "@tanstack/vue-query";
import { computed } from "vue";
import { listTrackedTasks, getTrackedTask, cancelTrackedTask } from "./api";
import { taskTrackerKeys } from "./keys";

export function useTrackedTasksQuery(kind?: () => "training" | "prediction" | undefined) {
  return useQuery({
    queryKey: computed(() => taskTrackerKeys.list(kind?.())),
    queryFn: () => listTrackedTasks(kind?.()),
    refetchInterval: 5000,
  });
}

export function useTrackedTaskQuery(taskId: () => string | null) {
  return useQuery({
    queryKey: computed(() => {
      const id = taskId();
      return id ? taskTrackerKeys.detail(id) : taskTrackerKeys.all;
    }),
    queryFn: ({ queryKey }) => getTrackedTask(queryKey[2] as string),
    enabled: computed(() => !!taskId()),
    refetchInterval: 5000,
  });
}

export function useCancelTrackedTaskMutation() {
  return useMutation({
    mutationFn: (id: string) => cancelTrackedTask(id),
  });
}
