import { describe, it, expect } from "vitest";
import { ref } from "vue";
import { usePerspectiveInspectionModel } from "../usePerspectiveInspectionModel";

describe("usePerspectiveInspectionModel.highlightDefectsForIds", () => {
  it("returns empty array when no table", async () => {
    const model = usePerspectiveInspectionModel({
      table: ref(null),
      legendGroupBy: ref("class"),
      tableFilter: ref({}),
      zoom: ref(null),
      activeMapMode: ref("wafer"),
    });
    const result = await model.highlightDefectsForIds([1, 2, 3]);
    expect(result).toEqual([]);
  });

  it("returns empty array when given empty ids", async () => {
    const model = usePerspectiveInspectionModel({
      table: ref(null),
      legendGroupBy: ref("class"),
      tableFilter: ref({}),
      zoom: ref(null),
      activeMapMode: ref("wafer"),
    });
    const result = await model.highlightDefectsForIds([]);
    expect(result).toEqual([]);
  });
});
