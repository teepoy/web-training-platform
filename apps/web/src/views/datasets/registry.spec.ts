import { describe, expect, it } from "vitest";

import { DATASET_SHIM_REGISTRY, resolveDatasetShim, resolveDatasetTaskType } from "./registry";

describe("dataset shim registry", () => {
  it("maps classification and vqa to their dedicated shims", () => {
    expect(resolveDatasetShim("classification")).toBe(DATASET_SHIM_REGISTRY.classification);
    expect(resolveDatasetShim("vqa")).toBe(DATASET_SHIM_REGISTRY.vqa);
  });

  it("falls back to the classification shim for missing or unknown task types", () => {
    expect(resolveDatasetShim(undefined)).toBe(DATASET_SHIM_REGISTRY.classification);
    expect(resolveDatasetShim("unsupported" as never)).toBe(DATASET_SHIM_REGISTRY.classification);
  });

  it("normalizes unsupported task types before shim resolution", () => {
    expect(resolveDatasetTaskType("unsupported")).toBe("classification");
    expect(() => resolveDatasetShim("unsupported")).not.toThrow();
  });
});
