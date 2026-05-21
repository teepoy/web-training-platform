import { describe, expect, it } from "vitest";

import { resolveDatasetShim, resolveDatasetTaskType } from "./registry";

describe("dataset shim registry", () => {
  it("maps dataset types to their dedicated shims", () => {
    const classificationShim = resolveDatasetShim("image_classification");
    const vqaShim = resolveDatasetShim("image_vqa");
    const detectionShim = resolveDatasetShim("image_detection");
    expect(classificationShim).toBeDefined();
    expect(vqaShim).toBeDefined();
    expect(detectionShim).toBeDefined();
    // Each dataset type resolves to a distinct shim
    expect(vqaShim).not.toBe(classificationShim);
    expect(detectionShim).not.toBe(classificationShim);
  });

  it("falls back to the classification shim for missing or unknown dataset types", () => {
    const fallback = resolveDatasetShim("image_classification");
    expect(resolveDatasetShim(undefined)).toBe(fallback);
    expect(resolveDatasetShim("unsupported" as never)).toBe(fallback);
  });

  it("normalizes unsupported task types before shim resolution", () => {
    expect(resolveDatasetTaskType("unsupported")).toBe("classification");
    expect(() => resolveDatasetShim("unsupported")).not.toThrow();
  });
});
