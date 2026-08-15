import { describe, expect, it } from "vitest";
import { shouldIgnoreSummaryRowClick } from "./summaryTableInteraction";

describe("shouldIgnoreSummaryRowClick", () => {
  it("keeps checkbox clicks from opening the inspection", () => {
    const checkbox = document.createElement("div");
    checkbox.setAttribute("role", "checkbox");
    const checkboxContent = document.createElement("span");
    checkbox.append(checkboxContent);

    expect(shouldIgnoreSummaryRowClick(checkboxContent)).toBe(true);
  });

  it("keeps dataset links and action buttons from opening the inspection", () => {
    expect(shouldIgnoreSummaryRowClick(document.createElement("a"))).toBe(true);
    expect(shouldIgnoreSummaryRowClick(document.createElement("button"))).toBe(true);
  });

  it("allows ordinary table cells to open the inspection", () => {
    expect(shouldIgnoreSummaryRowClick(document.createElement("td"))).toBe(false);
  });
});
