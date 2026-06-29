import { describe, it, expect } from "vitest";
import { binsToDisplayArray } from "@/features/sc/presentation/components/transforms/binsToDisplayArrays";
import type { MapBinRow } from "@/features/sc/presentation/components/composables/usePerspectiveMapView";

function makeBin(
  gx: number,
  gy: number,
  binSize: number,
  count: number,
  label: number,
  mis: number,
  imgs: number,
  gis: number,
): MapBinRow {
  return {
    gx,
    gy,
    binSize,
    count,
    map_in_selection: mis,
    images_has_review: imgs,
    gallery_in_selection: gis,
    _legendCol: "class_number",
    class_number: label,
  };
}

describe("binsToDisplayArray (Perspective 6-int format)", () => {
  it("encodes a single bin correctly", () => {
    const bin = makeBin(1, 2, 10, 5, 3, 0, 1, 0);
    const result = binsToDisplayArray([bin], "class_number");

    const x = 1 * 10 + 5; // gx * binSize + binSize/2 = 15
    const y = 2 * 10 + 5; // = 25
    expect(result).toBeInstanceOf(Float32Array);
    expect(Array.from(result)).toEqual([x, y, 3, 0, 1, 0]);
  });

  it("encodes map_in_selection flag", () => {
    const bin = makeBin(0, 0, 10, 1, 0, 1, 0, 0);
    const result = binsToDisplayArray([bin], "class_number");
    expect(result[3]).toBe(1); // map_in_selection at index 3
  });

  it("encodes has_images flag", () => {
    const bin = makeBin(0, 0, 10, 1, 0, 0, 1, 0);
    const result = binsToDisplayArray([bin], "class_number");
    expect(result[4]).toBe(1); // has_images at index 4
  });

  it("encodes gallery_in_selection flag", () => {
    const bin = makeBin(0, 0, 10, 1, 0, 0, 0, 1);
    const result = binsToDisplayArray([bin], "class_number");
    expect(result[5]).toBe(1); // gallery_in_selection at index 5
  });

  it("returns empty array for empty bins", () => {
    const result = binsToDisplayArray([], "class_number");
    expect(result).toBeInstanceOf(Float32Array);
    expect(result.length).toBe(0);
  });

  it("produces correct stride (6 per point)", () => {
    const bins = [makeBin(0, 0, 1, 1, 0, 0, 0, 0), makeBin(1, 1, 1, 1, 1, 0, 0, 0)];
    const result = binsToDisplayArray(bins, "class_number");
    expect(result.length).toBe(12); // 2 points x 6
  });
});
