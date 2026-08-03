import { describe, expect, it } from "vitest";
import { pointInPolygon } from "@platform/sc-map-element";

describe("pointInPolygon", () => {
  const triangle = [
    { x: 0, y: 0 },
    { x: 10, y: 0 },
    { x: 0, y: 10 },
  ];

  it("uses the lasso polygon rather than its bounding box", () => {
    expect(pointInPolygon({ x: 2, y: 2 }, triangle)).toBe(true);
    expect(pointInPolygon({ x: 8, y: 8 }, triangle)).toBe(false);
  });

  it("includes points on every lasso edge and vertex", () => {
    expect(pointInPolygon({ x: 0, y: 0 }, triangle)).toBe(true);
    expect(pointInPolygon({ x: 5, y: 0 }, triangle)).toBe(true);
    expect(pointInPolygon({ x: 5, y: 5 }, triangle)).toBe(true);
    expect(pointInPolygon({ x: 0, y: 5 }, triangle)).toBe(true);
  });
});
