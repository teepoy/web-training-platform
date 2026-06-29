import { describe, it, expect } from "vitest";
import { makePerspectiveStride6Points, makeHighlightDefects } from "./perspectiveMapFixtures";

describe("makePerspectiveStride6Points", () => {
  it("respects STRIDE=6 layout", () => {
    const { packed, points } = makePerspectiveStride6Points({
      count: 3,
      baseX: 100,
      baseY: 200,
    });
    expect(packed).toHaveLength(18);
    // First point at (100, 200)
    expect(packed[0]).toBe(100);
    expect(packed[1]).toBe(200);
    expect(packed[2]).toBe(0); // legendValue default
    expect(packed[3]).toBe(0); // mapInSelection default
    expect(packed[4]).toBe(0); // hasImages default
    expect(packed[5]).toBe(0); // galleryInSelection default
    // Second point at (110, 210) — default strideX/strideY=10
    expect(packed[6]).toBe(110);
    expect(packed[7]).toBe(210);
    expect(points).toHaveLength(3);
  });

  it("encodes boolean flags as 0/1 and propagates to typed points", () => {
    const { packed, points } = makePerspectiveStride6Points({
      count: 2,
      mapInSelection: true,
      galleryInSelection: true,
    });
    expect(packed[3]).toBe(1);
    expect(packed[5]).toBe(1);
    expect(points[0].mapInSelection).toBe(true);
    expect(points[0].galleryInSelection).toBe(true);
  });

  it("returns empty arrays when count=0", () => {
    const { packed, points } = makePerspectiveStride6Points({ count: 0 });
    expect(packed).toHaveLength(0);
    expect(points).toHaveLength(0);
  });
});

describe("makeHighlightDefects", () => {
  it("creates specified count of defects with auto-incrementing coordinates", () => {
    const result = makeHighlightDefects(3);
    expect(result).toHaveLength(3);
    expect(result[0].defectId).toBe(1);
    expect(result[0].waferX).toBe(1000);
    expect(result[2].waferX).toBe(1020);
  });
});
