import { describe, expect, it } from "vitest";
import { buildPerspectiveFilters } from "../perspectiveFilter";

describe("buildPerspectiveFilters", () => {
  it("builds set and inclusive range filters", () => {
    expect(
      buildPerspectiveFilters({
        test_id: { filterType: "set", values: [1, 2] },
        prediction_confidence: {
          filterType: "number",
          type: "inRange",
          filter: 0.5,
          filterTo: 0.9,
        },
      }),
    ).toEqual([
      ["test_id", "in", [1, 2]],
      ["prediction_confidence", ">=", 0.5],
      ["prediction_confidence", "<=", 0.9],
    ]);
  });

  it("omits the requested field for distinct-value queries", () => {
    expect(
      buildPerspectiveFilters(
        {
          test_id: { filterType: "set", values: [1] },
          final_class: { filterType: "set", values: ["Scratch"] },
        },
        { omitField: "test_id" },
      ),
    ).toEqual([["final_class", "in", ["Scratch"]]]);
  });
});
