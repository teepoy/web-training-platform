import { describe, it, expect } from "vitest";
import { floorMod, computeDieCoord } from "../useDieCoordinates";

describe("floorMod", () => {
  it("returns the remainder for a positive dividend", () => {
    expect(floorMod(7, 10)).toBe(7);
    expect(floorMod(3, 5)).toBe(3);
    expect(floorMod(0, 5)).toBe(0);
  });

  it("wraps negative results into the positive range", () => {
    expect(floorMod(-5, 10)).toBe(5);
    expect(floorMod(-1, 10)).toBe(9);
    expect(floorMod(-3, 5)).toBe(2);
  });

  it("handles exact multiples of the divisor", () => {
    expect(floorMod(10, 10)).toBe(0);
    expect(floorMod(-10, 10)).toBe(0);
    expect(floorMod(0, 10)).toBe(0);
  });

  it("handles large negative numbers", () => {
    expect(floorMod(-15, 10)).toBe(5);
    expect(floorMod(-25, 10)).toBe(5);
    expect(floorMod(-100, 7)).toBe(5);
  });

  it("handles negative value larger than the modulus magnitude (e.g. -5 % 10)", () => {
    // JS: -5 % 10 === -5, floorMod wraps: (-5 + 10) % 10 === 5
    expect(floorMod(-5, 10)).toBe(5);
  });

  it("handles large numbers typical of wafer coordinates", () => {
    expect(floorMod(150_000_005, 20_000)).toBe(5);
    expect(floorMod(-20_000, 20_000)).toBe(0);
    expect(floorMod(-30_000, 20_000)).toBe(10_000);
  });
});

describe("computeDieCoord", () => {
  // Typical SC values: origin ~150M, wafer ~0-300M, die_size ~20K
  const ORIGIN = 150_000_000;
  const DIE_SIZE = 20_000;

  it("returns 0 when waferCoord equals origin", () => {
    expect(computeDieCoord(ORIGIN, ORIGIN, DIE_SIZE)).toBe(0);
  });

  it("computes positive offset from origin", () => {
    // waferCoord = origin + 2 * die_size
    expect(computeDieCoord(ORIGIN + 2 * DIE_SIZE, ORIGIN, DIE_SIZE)).toBe(0);
    // waferCoord = origin + die_size + 5
    expect(computeDieCoord(ORIGIN + DIE_SIZE + 5, ORIGIN, DIE_SIZE)).toBe(5);
  });

  it("wraps negative offset via floorMod", () => {
    // waferCoord 20K below origin → wraps to 0
    expect(computeDieCoord(ORIGIN - DIE_SIZE, ORIGIN, DIE_SIZE)).toBe(0);
    // waferCoord 30K below origin → wraps to 10K
    expect(computeDieCoord(ORIGIN - 30_000, ORIGIN, DIE_SIZE)).toBe(10_000);
  });

  it("handles waferCoord well above origin (typical SC range)", () => {
    // wafer_x ~200M, origin ~150M, difference 50M, die 20K → 50M % 20K = 0
    expect(computeDieCoord(200_000_000, ORIGIN, DIE_SIZE)).toBe(0);
    // wafer_x ~200_000_007, different 50_000_007 → 7
    expect(computeDieCoord(200_000_007, ORIGIN, DIE_SIZE)).toBe(7);
  });

  it("handles waferCoord below origin (wrapped around)", () => {
    // waferCoord 100M, origin 150M, diff = -50M, die 20K → 0
    expect(computeDieCoord(100_000_000, ORIGIN, DIE_SIZE)).toBe(0);
    // waferCoord 149_970_000, origin 150M, diff = -30K → 10K
    expect(computeDieCoord(149_970_000, ORIGIN, DIE_SIZE)).toBe(10_000);
  });

  it("handles zero die_size edge case gracefully", () => {
    // floorMod(any, 0) → NaN (division by zero)
    expect(computeDieCoord(100, 0, 0)).toBeNaN();
  });
});
