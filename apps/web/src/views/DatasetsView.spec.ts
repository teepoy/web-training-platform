import { describe, expect, it } from "vitest";

import type { Dataset, TaskSpec } from "../types";
import { DATASET_SHIM_REGISTRY, resolveDatasetShim } from "./datasets/registry";
import { getActiveDatasetTaskType } from "./datasets/selection";

function makeDataset(taskType: Dataset["task_spec"]["task_type"]): Dataset {
  return {
    id: `${taskType}-dataset`,
    name: `${taskType} dataset`,
    dataset_type: taskType === "vqa" ? "image_vqa" : "image_classification",
    task_spec: {
      task_type: taskType,
      label_space: ["label-a"],
    },
    created_at: "2026-05-08T00:00:00.000Z",
    storage_mode: "db_full",
  };
}

function makeMalformedDataset(overrides: Omit<Partial<Dataset>, "task_spec"> & { task_spec?: TaskSpec | null }): Dataset {
  return {
    id: overrides.id ?? "malformed-dataset",
    name: overrides.name ?? "malformed dataset",
    dataset_type: overrides.dataset_type ?? "image_classification",
    created_at: overrides.created_at ?? "2026-05-08T00:00:00.000Z",
    storage_mode: "db_full",
    ...overrides,
  } as Dataset;
}

describe("DatasetsView host delegation", () => {
  it("reads the first dataset task type when present", () => {
    expect(getActiveDatasetTaskType([makeDataset("vqa")])).toBe("vqa");
  });

  it("falls back to classification when the first row is missing task_spec", () => {
    const datasetType = getActiveDatasetTaskType([makeMalformedDataset({ task_spec: undefined })]);

    expect(datasetType).toBe(undefined);
    expect(() => resolveDatasetShim(datasetType)).not.toThrow();
    expect(resolveDatasetShim(datasetType)).toBe(DATASET_SHIM_REGISTRY.classification);
  });

  it("falls back to classification when the first row has a null task_spec", () => {
    const datasetType = getActiveDatasetTaskType([makeMalformedDataset({ task_spec: null })]);

    expect(datasetType).toBe(undefined);
    expect(() => resolveDatasetShim(datasetType)).not.toThrow();
    expect(resolveDatasetShim(datasetType)).toBe(DATASET_SHIM_REGISTRY.classification);
  });

  it("falls back to classification for unknown task_spec task types", () => {
    const datasetType = getActiveDatasetTaskType([
      makeMalformedDataset({
        task_spec: {
          task_type: "unsupported" as never,
          label_space: ["label-a"],
        },
      }),
    ]);

    expect(datasetType).toBe("unsupported");
    expect(() => resolveDatasetShim(datasetType)).not.toThrow();
    expect(resolveDatasetShim(datasetType)).toBe(DATASET_SHIM_REGISTRY.classification);
  });

  it("returns undefined when datasets are absent or empty", () => {
    expect(getActiveDatasetTaskType(undefined)).toBe(undefined);
    expect(getActiveDatasetTaskType(null)).toBe(undefined);
    expect(getActiveDatasetTaskType([])).toBe(undefined);
  });
});
