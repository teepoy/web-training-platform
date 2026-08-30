import { describe, expect, it } from "vitest";
import {
  formatScClassNumber,
  normalizeScClassNumber,
  resolveScClassNumberDisplayName,
  SC_CLASS_NUMBER_DISPLAY_NAMES,
} from "./classNumberDisplay";

describe("SC class-number display registry", () => {
  it("resolves the existing platform class names", () => {
    expect(SC_CLASS_NUMBER_DISPLAY_NAMES["0"]).toBe("Unclassified");
    expect(resolveScClassNumberDisplayName(0)).toBe("Unclassified");
    expect(resolveScClassNumberDisplayName("7")).toBe("Code 7");
    expect(formatScClassNumber(7)).toBe("7 · Code 7");
  });

  it("keeps unknown integer values visible as their raw number", () => {
    expect(resolveScClassNumberDisplayName(99)).toBe("99");
    expect(formatScClassNumber(99)).toBe("99");
  });

  it("normalizes numeric input without changing the raw filter identity", () => {
    expect(normalizeScClassNumber("12")).toBe(12);
    expect(normalizeScClassNumber(12)).toBe(12);
    expect(normalizeScClassNumber("not-a-class")).toBeNull();
  });
});
