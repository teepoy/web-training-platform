import { describe, expect, it } from "vitest";
import {
  SC_RECLASSIFY_TABLE_COLUMNS,
  SC_SAMPLE_TABLE_COLUMNS,
  scGlobalFilterColumns,
  scSampleTableColumns,
} from "./scSampleTableColumns";

function fieldNames(columns: Array<{ key: string }>): string[] {
  return columns.map((column) => String(column.key));
}

describe("SC sample table filter columns", () => {
  it("offers every preview table field as a global filter", () => {
    expect(fieldNames(scGlobalFilterColumns(false))).toEqual(
      fieldNames(scSampleTableColumns(false)),
    );
  });

  it("offers every reclassify table field and final class as global filters", () => {
    const globalFields = fieldNames(scGlobalFilterColumns(true));

    expect(globalFields).toEqual([
      ...fieldNames(SC_SAMPLE_TABLE_COLUMNS),
      ...fieldNames(SC_RECLASSIFY_TABLE_COLUMNS),
      "final_class",
    ]);
    expect(globalFields).toContain("annotation_label");
    expect(globalFields).toContain("prediction_confidence");
  });
});
