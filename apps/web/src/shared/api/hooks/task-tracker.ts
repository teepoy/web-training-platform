import { useQuery, useMutation, type UseQueryOptions } from "@tanstack/vue-query";
import { computed } from "vue";
import {
  listTrackedTasks,
  getTrackedTask,
  cancelTrackedTask,
} from "../task-tracker";

export const taskTrackerKeys = {
  all: ["task-tracker"] as const,
  list: (kind?: string) => ["task-tracker", "list", kind ?? "all"] as const,
  detail: (id: string) => ["task-tracker", "detail", id] as const,
};

export function useTrackedTasksQuery(
  kind?: () => "training" | "prediction" | undefined,
  options?: Partial<UseQueryOptions<Awaited<ReturnType<typeof listTrackedTasks>>>>,
) {
  return useQuery({
    queryKey: computed(() => taskTrackerKeys.list(kind?.())),
    queryFn: () => listTrackedTasks(kind?.()),
    refetchInterval: 5000,
    ...options,
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
