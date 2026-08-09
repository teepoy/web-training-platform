import { describe, expect, it } from "vitest";
import type { ScDataColumn } from "@/features/sc/domain/workbenchDataSource";
import { scGlobalFilterColumns, scSampleTableColumns } from "./scSampleTableColumns";

function column(
  name: string,
  order: number,
  visibility: NonNullable<ScDataColumn["presentation"]>["visibility"] = "default",
): ScDataColumn {
  return {
    name,
    arrowType: name.includes("confidence") ? "Float64" : "Utf8",
    nullable: true,
    presentation: {
      title: name,
      width: 120,
      filter: name.includes("confidence") ? "range" : "set",
      visibility,
      format: "plain",
      order,
    },
  };
}

const columns = [
  column("defect_id", 0),
  column("annotation_label", 1, "reclassify"),
  column("prediction_confidence", 2, "reclassify"),
  column("final_class", 3, "filter_only"),
  column("sample_id", 4, "internal"),
];

function fieldNames(items: Array<{ key: string }>): string[] {
  return items.map((item) => item.key);
}

describe("SC sample-table descriptor projection", () => {
  it("uses default columns for preview tables and global filters", () => {
    expect(fieldNames(scSampleTableColumns(columns, false))).toEqual(["defect_id"]);
    expect(fieldNames(scGlobalFilterColumns(columns, false))).toEqual(["defect_id"]);
  });

  it("adds reclassify and filter-only properties without exposing internals", () => {
    expect(fieldNames(scSampleTableColumns(columns, true))).toEqual([
      "defect_id",
      "annotation_label",
      "prediction_confidence",
    ]);
    expect(fieldNames(scGlobalFilterColumns(columns, true))).toEqual([
      "defect_id",
      "annotation_label",
      "prediction_confidence",
      "final_class",
    ]);
  });

  it("keeps unknown physical metadata columns visible and filterable", () => {
    const dynamic = { name: "future_metric", arrowType: "Float64", nullable: true };

    expect(scSampleTableColumns([...columns, dynamic], false).at(-1)).toMatchObject({
      key: "future_metric",
      title: "future_metric",
      filter: "range",
    });
  });
});
