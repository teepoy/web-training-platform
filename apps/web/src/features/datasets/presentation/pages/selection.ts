import type { Dataset } from "@/features/datasets/domain/models";

export function getActiveDatasetTaskType(datasets: Dataset[] | null | undefined): string | undefined {
  if (!datasets || datasets.length === 0) {
    return undefined;
  }

  return datasets[0].task_spec?.task_type;
}

export function getActiveDatasetType(datasets: Dataset[] | null | undefined): string | undefined {
  if (!datasets || datasets.length === 0) {
    return undefined;
  }

  return datasets[0].dataset_type;
}
