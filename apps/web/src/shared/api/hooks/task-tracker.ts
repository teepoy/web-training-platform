import { useQuery, type UseQueryOptions } from "@tanstack/vue-query";
import { computed } from "vue";
import { getTaskTrackerTaskApiV1TaskTrackerTasksTaskIdGet } from "@/generated/orval/endpoints/api";
import { listTrackedTasks } from "../task-tracker";

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
    queryFn: ({ queryKey }) =>
      getTaskTrackerTaskApiV1TaskTrackerTasksTaskIdGet(queryKey[2] as string),
    enabled: computed(() => !!taskId()),
    refetchInterval: 5000,
  });
}
