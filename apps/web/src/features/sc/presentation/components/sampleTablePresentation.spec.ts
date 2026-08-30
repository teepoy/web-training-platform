import { describe, expect, it } from "vitest";
import type { ScDataColumn } from "@/features/sc/domain/workbenchDataSource";
import {
  normalizeSampleTableFilterValue,
  renderSampleTableCell,
  sampleTablePresentationColumns,
} from "./sampleTablePresentation";

const classColumn: ScDataColumn = {
  name: "class_number",
  arrowType: "Int32",
  nullable: false,
  presentation: {
    title: "Class",
    width: 120,
    filter: "set",
    visibility: "default",
    format: "plain",
    order: 0,
  },
};

describe("SC sample-table class-number presentation", () => {
  it("adds the canonical display name without changing the row value", () => {
    const [definition] = sampleTablePresentationColumns([classColumn], false);
    const row = {
      row_key: "dataset::sample-1",
      defect_id: "1",
      class_number: 7,
      _isHydrated: true,
    };

    expect(renderSampleTableCell(definition!, row)).toBe("7 · Code 7");
    expect(row.class_number).toBe(7);
  });

  it("shows an unknown class as its raw number and keeps filters numeric", () => {
    const [definition] = sampleTablePresentationColumns([classColumn], false);
    expect(
      renderSampleTableCell(definition!, {
        row_key: "dataset::sample-2",
        defect_id: "2",
        class_number: 99,
        _isHydrated: true,
      }),
    ).toBe("99");
    expect(normalizeSampleTableFilterValue("class_number", 99)).toBe(99);
  });
});
