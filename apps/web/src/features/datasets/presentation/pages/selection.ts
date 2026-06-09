import type { Dataset } from "@/generated/orval/models";

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

export function getActiveViewTypes(datasets: Dataset[] | null | undefined): string[] | undefined {
  if (!datasets || datasets.length === 0) {
    return undefined;
  }

  const ds = datasets[0] as any;
  return ds.view_types;
}
