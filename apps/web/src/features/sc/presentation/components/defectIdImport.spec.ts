import { describe, expect, it } from "vitest";
import { parseDefectIds } from "./defectIdImport";

describe("parseDefectIds", () => {
  it("parses, deduplicates, and validates pasted ID lists", () => {
    expect(parseDefectIds("1001, 1002\n1001 invalid 1.5 1003")).toEqual({
      values: [1001, 1002, 1003],
      invalidCount: 2,
    });
  });

  it("selects the defect_id column from a CSV export", () => {
    expect(parseDefectIds("class_number,defect_id,area\n7,4201,12.5\n8,4202,18.2")).toEqual({
      values: [4201, 4202],
      invalidCount: 0,
    });
  });

  it("supports quoted CSV headers and values", () => {
    expect(parseDefectIds('"defect id","label"\n"9001","scratch"')).toEqual({
      values: [9001],
      invalidCount: 0,
    });
  });

  it("keeps a large imported list complete and ordered", () => {
    const content = Array.from({ length: 100_000 }, (_, index) => String(index + 1)).join("\n");

    const parsed = parseDefectIds(content);

    expect(parsed.values).toHaveLength(100_000);
    expect(parsed.values[0]).toBe(1);
    expect(parsed.values[99_999]).toBe(100_000);
    expect(parsed.invalidCount).toBe(0);
  });
});
