import type { TaskType } from "@/shared/api/types";

export function resolveDatasetTaskType(taskType: string | null | undefined): TaskType {
  if (taskType === "sc") return "sc";
  return "classification";
}
