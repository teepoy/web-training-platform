import type { TaskType } from "@/features/datasets/domain/models";

export { resolveDatasetShim, getDatasetSchema, listRegisteredDatasetTypes } from "./schema-registry";

export function resolveDatasetTaskType(taskType: string | null | undefined): TaskType {
  if (taskType === "vqa") return "vqa";
  if (taskType === "detection") return "detection";
  return "classification";
}
