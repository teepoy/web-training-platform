import {
  listTaskTrackerTasksApiV1TaskTrackerTasksGet,
  getTaskTrackerTaskApiV1TaskTrackerTasksTaskIdGet,
  cancelTaskTrackerTaskApiV1TaskTrackerTasksTaskIdCancelPost,
} from "@/generated/orval/endpoints/api";
import type {
  TaskTrackerSummaryResponse as TaskTrackerSummary,
  TaskTrackerDetailResponse as TaskTrackerDetail,
} from "@/generated/orval/models";

export async function listTrackedTasks(
  kind?: "training" | "prediction",
): Promise<TaskTrackerSummary[]> {
  const tasks: TaskTrackerSummary[] = [];
  const pageSize = 200;
  let offset = 0;
  while (true) {
    const response = await listTaskTrackerTasksApiV1TaskTrackerTasksGet({
      kind,
      offset,
      limit: pageSize,
    });
    const page = response.data;
    if (!("items" in page)) {
      throw new Error("Failed to list tracked tasks");
    }
    tasks.push(...page.items);
    if (tasks.length >= page.total) {
      return tasks;
    }
    if (page.items.length === 0) {
      throw new Error("Task tracker pagination returned an incomplete empty page");
    }
    offset += page.items.length;
  }
}

export async function getTrackedTask(id: string): Promise<TaskTrackerDetail> {
  return (await getTaskTrackerTaskApiV1TaskTrackerTasksTaskIdGet(id)).data as TaskTrackerDetail;
}

export async function cancelTrackedTask(id: string): Promise<{ cancelled: boolean }> {
  return (await cancelTaskTrackerTaskApiV1TaskTrackerTasksTaskIdCancelPost(id)).data as {
    cancelled: boolean;
  };
}
