import type { TaskType } from "@/features/datasets/domain/models";

// Import schema modules to trigger auto-registration
import "./schemas/image-classification";
import "./schemas/image-vqa";
import "./schemas/image-detection";

export { resolveDatasetShim, getDatasetSchema, listRegisteredDatasetTypes } from "./schema-registry";

export function resolveDatasetTaskType(taskType: string | null | undefined): TaskType {
  if (taskType === "vqa") return "vqa";
  if (taskType === "detection") return "detection";
  return "classification";
}
