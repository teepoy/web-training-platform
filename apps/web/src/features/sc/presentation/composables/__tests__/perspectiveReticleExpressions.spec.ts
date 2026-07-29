import { describe, expect, it } from "vitest";
import { perspectiveReticleExpressions } from "../perspectiveReticleExpressions";

describe("perspectiveReticleExpressions", () => {
  it("computes reticle coordinates from die position, die index, count, and shift", () => {
    expect(
      perspectiveReticleExpressions(
        { xDieCount: 3, yDieCount: 5, xDieShift: -1, yDieShift: 2 },
        { dieSizeX: 100_000, dieSizeY: 200_000 },
      ),
    ).toEqual({
      reticle_x: '"die_x" + (((("index_x" + -1) % 3) + 3) % 3 * 100000)',
      reticle_y: '"die_y" + (((("index_y" + 2) % 5) + 5) % 5 * 200000)',
    });
  });

  it("rejects invalid die geometry", () => {
    expect(() =>
      perspectiveReticleExpressions(
        { xDieCount: 3, yDieCount: 5, xDieShift: 0, yDieShift: 0 },
        { dieSizeX: 0, dieSizeY: 1 },
      ),
    ).toThrow("positive die dimensions");
  });
});
