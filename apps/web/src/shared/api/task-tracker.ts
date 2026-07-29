import { listTaskTrackerTasksApiV1TaskTrackerTasksGet } from "@/generated/orval/endpoints/api";
import type { TaskTrackerSummaryResponse as TaskTrackerSummary } from "@/generated/orval/models";

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
    const page = response;
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
