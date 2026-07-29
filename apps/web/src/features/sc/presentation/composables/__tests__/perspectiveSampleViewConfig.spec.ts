import { describe, expect, it } from "vitest";
import { buildPerspectiveSampleViewConfig } from "../perspectiveSampleViewConfig";

describe("buildPerspectiveSampleViewConfig", () => {
  it("combines context, selection, and table-header filters in a stable order", () => {
    expect(
      buildPerspectiveSampleViewConfig({
        base: {
          columns: ["defect_id"],
          filter: [["rough_bin", "==", 1]],
        },
        additionalFilters: [["table_in_selection", "==", 1]],
        tableFilter: {
          class_number: { filterType: "set", values: [2, 3] },
        },
        tableSort: { field: "class_number", direction: "desc" },
      }),
    ).toEqual({
      columns: ["defect_id"],
      filter: [
        ["rough_bin", "==", 1],
        ["table_in_selection", "==", 1],
        ["class_number", "in", [2, 3]],
      ],
      sort: [["class_number", "desc"]],
    });
  });

  it("uses defect_id ascending and can omit the current header field", () => {
    expect(
      buildPerspectiveSampleViewConfig({
        tableFilter: {
          rough_bin: { filterType: "set", values: [1] },
          class_number: { filterType: "set", values: [2] },
        },
        omitTableFilterField: "rough_bin",
      }),
    ).toEqual({
      filter: [["class_number", "in", [2]]],
      sort: [["defect_id", "asc"]],
    });
  });
});
