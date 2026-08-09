import { describe, expect, it } from "vitest";
import { combineMapSelectionIds } from "@platform/sc-map-element";

function sorted(values: ReadonlySet<number>): number[] {
  return [...values].sort((left, right) => left - right);
}

describe("Map Arrow selection set operations", () => {
  it("appends and replaces exact map IDs", () => {
    expect(sorted(combineMapSelectionIds(new Set([2, 7]), new Set([7, 9]), "append"))).toEqual([
      2, 7, 9,
    ]);
    expect(sorted(combineMapSelectionIds(new Set([2, 7]), new Set([9]), "replace"))).toEqual([9]);
  });

  it("prunes to visible IDs and inverts within the visible universe", () => {
    expect(sorted(combineMapSelectionIds(new Set([2, 7, 9]), new Set([2, 9]), "prune"))).toEqual([
      2, 9,
    ]);
    expect(
      sorted(combineMapSelectionIds(new Set([2, 7]), new Set([2, 7, 9, 11]), "invert")),
    ).toEqual([9, 11]);
  });

  it("clears without retaining candidates", () => {
    expect(sorted(combineMapSelectionIds(new Set([2, 7]), new Set([9]), "clear"))).toEqual([]);
  });
});
