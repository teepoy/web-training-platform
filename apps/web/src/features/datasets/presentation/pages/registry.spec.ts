import { describe, expect, it } from "vitest";

import "../dataset-types/classification/views/schema";
import { getDatasetSchema, resolveDatasetShim } from "./schema-registry";
import { resolveDatasetTaskType } from "./registry";

describe("dataset shim registry", () => {
  it("maps dataset types to their dedicated shims", () => {
    expect(getDatasetSchema("image_classification")).toBeDefined();
    expect(() => resolveDatasetShim("image_classification")).not.toThrow();
  });

  it("falls back to the classification shim for missing or unknown dataset types", () => {
    expect(() => resolveDatasetShim(undefined)).not.toThrow();
    expect(() => resolveDatasetShim("unsupported" as never)).not.toThrow();
  });

  it("normalizes unsupported task types before shim resolution", () => {
    expect(resolveDatasetTaskType("unsupported")).toBe("classification");
    expect(() => resolveDatasetShim("unsupported")).not.toThrow();
  });
});
