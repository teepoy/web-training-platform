import {
  listTaskTrackerTasksApiV1TaskTrackerTasksGet,
  getTaskTrackerTaskApiV1TaskTrackerTasksTaskIdGet,
  cancelTaskTrackerTaskApiV1TaskTrackerTasksTaskIdCancelPost,
} from "@/generated/orval/endpoints/api";
import type { TaskTrackerSummaryResponse as TaskTrackerSummary, TaskTrackerDetailResponse as TaskTrackerDetail } from "@/generated/orval/models";

export async function listTrackedTasks(
  kind?: "training" | "prediction",
): Promise<TaskTrackerSummary[]> {
  return (await
    listTaskTrackerTasksApiV1TaskTrackerTasksGet(kind ? { kind } : undefined)).data as TaskTrackerSummary[];
}

export async function getTrackedTask(id: string): Promise<TaskTrackerDetail> {
  return (await
    getTaskTrackerTaskApiV1TaskTrackerTasksTaskIdGet(id)).data as TaskTrackerDetail;
}

export async function cancelTrackedTask(id: string): Promise<{ cancelled: boolean }> {
  return (await
    cancelTaskTrackerTaskApiV1TaskTrackerTasksTaskIdCancelPost(id)).data as { cancelled: boolean };
}
