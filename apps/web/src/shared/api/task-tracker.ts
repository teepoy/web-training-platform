import { req } from "./client";
import type {
  TaskTrackerSummary,
  TaskTrackerDetail,
} from "./types";

export function listTrackedTasks(
  kind?: "training" | "prediction",
): Promise<TaskTrackerSummary[]> {
  const qs = kind ? `?kind=${encodeURIComponent(kind)}` : "";
  return req<TaskTrackerSummary[]>(`/task-tracker/tasks${qs}`);
}

export function getTrackedTask(id: string): Promise<TaskTrackerDetail> {
  return req<TaskTrackerDetail>(`/task-tracker/tasks/${id}`);
}

export function cancelTrackedTask(
  id: string,
): Promise<{ cancelled: boolean }> {
  return req<{ cancelled: boolean }>(`/task-tracker/tasks/${id}/cancel`, {
    method: "POST",
  });
}
