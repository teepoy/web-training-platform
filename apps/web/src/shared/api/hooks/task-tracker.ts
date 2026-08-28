import { useQuery, type UseQueryOptions } from "@tanstack/vue-query";
import { computed, toValue, type MaybeRefOrGetter } from "vue";
import { getTaskTrackerTaskApiV1TaskTrackerTasksTaskIdGet } from "@/generated/orval/endpoints/api";
import { listTrackedTasks } from "../task-tracker";
import type { ListTaskTrackerTasksApiV1TaskTrackerTasksGetParams } from "@/generated/orval/models";

export const taskTrackerKeys = {
  all: ["task-tracker"] as const,
  list: (params: ListTaskTrackerTasksApiV1TaskTrackerTasksGetParams) =>
    ["task-tracker", "list", params] as const,
  detail: (id: string) => ["task-tracker", "detail", id] as const,
};

export function useTrackedTasksQuery(
  params: MaybeRefOrGetter<ListTaskTrackerTasksApiV1TaskTrackerTasksGetParams>,
  options?: Partial<UseQueryOptions<Awaited<ReturnType<typeof listTrackedTasks>>>>,
) {
  return useQuery({
    queryKey: computed(() => taskTrackerKeys.list(toValue(params))),
    queryFn: () => listTrackedTasks(toValue(params)),
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
