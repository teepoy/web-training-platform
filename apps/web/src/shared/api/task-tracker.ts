import { listTaskTrackerTasksApiV1TaskTrackerTasksGet } from "@/generated/orval/endpoints/api";
import type { ListTaskTrackerTasksApiV1TaskTrackerTasksGetParams } from "@/generated/orval/models";

export async function listTrackedTasks(
  params: ListTaskTrackerTasksApiV1TaskTrackerTasksGetParams = {},
) {
  return listTaskTrackerTasksApiV1TaskTrackerTasksGet(params);
}
