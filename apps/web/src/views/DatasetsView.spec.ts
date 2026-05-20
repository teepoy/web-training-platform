import { describe, expect, it } from "vitest";

import type { Dataset, TaskSpec } from "../types";
import { resolveDatasetShim } from "./datasets/registry";
import { getActiveDatasetTaskType, getActiveDatasetType } from "./datasets/selection";

function makeDataset(taskType: Dataset["task_spec"]["task_type"]): Dataset {
  const datasetType = taskType === "vqa" ? "image_vqa" : taskType === "detection" ? "image_detection" : "image_classification";
  return {
    id: `${taskType}-dataset`,
    name: `${taskType} dataset`,
    dataset_type: datasetType,
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

const classificationShim = resolveDatasetShim("image_classification");

describe("DatasetsView host delegation", () => {
  it("reads the first dataset task type when present", () => {
    expect(getActiveDatasetTaskType([makeDataset("vqa")])).toBe("vqa");
  });

  it("reads the first dataset type when present", () => {
    expect(getActiveDatasetType([makeDataset("vqa")])).toBe("image_vqa");
    expect(getActiveDatasetType([makeDataset("detection")])).toBe("image_detection");
  });

  it("falls back to classification shim when the first row is missing task_spec", () => {
    const ds = [makeMalformedDataset({ task_spec: undefined })];
    const activeDatasetType = getActiveDatasetType(ds);

    expect(activeDatasetType).toBe("image_classification"); // default in makeDataset
    expect(() => resolveDatasetShim(activeDatasetType)).not.toThrow();
    expect(resolveDatasetShim(activeDatasetType)).toBe(classificationShim);
  });

  it("falls back to classification shim when the first row has a null task_spec", () => {
    const ds = [makeMalformedDataset({ task_spec: null })];
    const activeDatasetType = getActiveDatasetType(ds);

    expect(activeDatasetType).toBe("image_classification");
    expect(() => resolveDatasetShim(activeDatasetType)).not.toThrow();
    expect(resolveDatasetShim(activeDatasetType)).toBe(classificationShim);
  });

  it("falls back to classification shim for unknown dataset types", () => {
    const ds = [makeMalformedDataset({ dataset_type: "unsupported" as never })];
    const activeDatasetType = getActiveDatasetType(ds);

    expect(activeDatasetType).toBe("unsupported");
    expect(() => resolveDatasetShim(activeDatasetType)).not.toThrow();
    expect(resolveDatasetShim(activeDatasetType)).toBe(classificationShim);
  });

  it("resolves distinct shims for each known dataset type", () => {
    expect(resolveDatasetShim("image_vqa")).not.toBe(classificationShim);
    expect(resolveDatasetShim("image_detection")).not.toBe(classificationShim);
  });

  it("returns undefined when datasets are absent or empty", () => {
    expect(getActiveDatasetTaskType(undefined)).toBe(undefined);
    expect(getActiveDatasetTaskType(null)).toBe(undefined);
    expect(getActiveDatasetTaskType([])).toBe(undefined);
    expect(getActiveDatasetType(undefined)).toBe(undefined);
    expect(getActiveDatasetType(null)).toBe(undefined);
    expect(getActiveDatasetType([])).toBe(undefined);
  });
});
