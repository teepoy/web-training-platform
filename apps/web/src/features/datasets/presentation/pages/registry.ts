import type { TaskType } from "@/shared/api/types";

export function resolveDatasetTaskType(taskType: string | null | undefined): TaskType {
  if (taskType === "vqa") return "vqa";
  if (taskType === "detection") return "detection";
  return "classification";
}
