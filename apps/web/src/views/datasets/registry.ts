import { defineAsyncComponent, type Component } from "vue";

import type { TaskType } from "../../types";

export function resolveDatasetTaskType(taskType: string | null | undefined): TaskType {
  return taskType === "vqa" ? "vqa" : "classification";
}

export const DATASET_SHIM_REGISTRY = {
  classification: defineAsyncComponent(() => import("./shims/ClassificationDatasetsShim.vue")),
  vqa: defineAsyncComponent(() => import("./shims/VqaDatasetsShim.vue")),
} satisfies Record<TaskType, Component>;

export function resolveDatasetShim(taskType: string | null | undefined): Component {
  if (resolveDatasetTaskType(taskType) === "vqa") {
    return DATASET_SHIM_REGISTRY.vqa;
  }

  return DATASET_SHIM_REGISTRY.classification;
}
