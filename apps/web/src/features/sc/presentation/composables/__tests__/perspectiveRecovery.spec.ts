import { describe, expect, it } from "vitest";

import {
  isRecoverablePerspectiveError,
  perspectiveErrorMessage,
} from "../perspectiveRecovery";

describe("perspectiveRecovery", () => {
  it("treats wasm memory access failures as recoverable", () => {
    expect(
      isRecoverablePerspectiveError(new WebAssembly.RuntimeError("memory access out of bounds")),
    ).toBe(true);
  });

  it("does not recover for ordinary validation errors", () => {
    expect(isRecoverablePerspectiveError(new Error("unknown column class_name"))).toBe(false);
  });

  it("normalizes non-error messages", () => {
    expect(perspectiveErrorMessage("connection closed")).toBe("connection closed");
  });
});
