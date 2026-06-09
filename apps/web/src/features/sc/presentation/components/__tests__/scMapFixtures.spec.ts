import { describe, it, expect } from "vitest";
import {
  makeStride6Points,
  EMPTY_POINTS,
  SINGLE_POINT,
  MIXED_CLASS_POINTS,
  LEGACY_RETICLE_TRIPLES,
  LARGE_POINTS,
} from "./scMapFixtures";

const STRIDE = 6;

describe("makeStride6Points", () => {
  it("returns array of count * 6 length", () => {
    const points = makeStride6Points(3);
    expect(points).toHaveLength(18);
  });

  it("returns stable/deterministic output for same inputs", () => {
    const a = makeStride6Points(5, { startId: 10, classSeed: 1 });
    const b = makeStride6Points(5, { startId: 10, classSeed: 1 });
    expect(a).toEqual(b);
  });

  it("returns different output for different startId", () => {
    const a = makeStride6Points(2, { startId: 1 });
    const b = makeStride6Points(2, { startId: 100 });
    // defectId field (index 2, 8) should differ
    expect(a[2]).not.toBe(b[2]);
    expect(a[8]).not.toBe(b[8]);
  });

  it("cycles classes based on classSeed", () => {
    const seed0 = makeStride6Points(4, { classSeed: 0 });
    const seed1 = makeStride6Points(4, { classSeed: 1 });
    // classNumber field (index 3, 9, 15, 21) — shifted by seed
    expect(seed0[3]).toBe(0); // (0+0)%3 = 0
    expect(seed1[3]).toBe(1); // (0+1)%3 = 1
    expect(seed0[9]).toBe(1); // (1+0)%3 = 1
    expect(seed1[9]).toBe(2); // (1+1)%3 = 2
  });

  it("defaults startId to 1", () => {
    const points = makeStride6Points(2);
    expect(points[2]).toBe(1); // first defectId
    expect(points[8]).toBe(2); // second defectId
  });

  it("handles count=0", () => {
    const points = makeStride6Points(0);
    expect(points).toHaveLength(0);
  });

  it("handles count=1", () => {
    const points = makeStride6Points(1);
    expect(points).toHaveLength(STRIDE);
  });

  it("generates 10 000 points = 60 000 ints", () => {
    const points = makeStride6Points(10_000);
    expect(points).toHaveLength(60_000);
  });
});

describe("EMPTY_POINTS", () => {
  it("is an empty array", () => {
    expect(EMPTY_POINTS).toEqual([]);
    expect(EMPTY_POINTS).toHaveLength(0);
  });
});

describe("SINGLE_POINT", () => {
  it("has length 6", () => {
    expect(SINGLE_POINT).toHaveLength(6);
  });

  it("has expected structure", () => {
    const [x, y, id, cls, bin, rev] = SINGLE_POINT;
    expect(x).toBe(100);
    expect(y).toBe(200);
    expect(id).toBe(1);
    expect(cls).toBe(1);
    expect(bin).toBe(0);
    expect(rev).toBe(0);
  });
});

describe("MIXED_CLASS_POINTS", () => {
  it("has length 24 (4 points × STRIDE=6)", () => {
    expect(MIXED_CLASS_POINTS).toHaveLength(24);
  });

  it("groups points by expected class", () => {
    const classGroups = new Map<number, number[]>();
    for (let i = 0; i < MIXED_CLASS_POINTS.length; i += STRIDE) {
      const cls = MIXED_CLASS_POINTS[i + 3];
      const id = MIXED_CLASS_POINTS[i + 2];
      if (!classGroups.has(cls)) classGroups.set(cls, []);
      classGroups.get(cls)!.push(id);
    }

    // class 1: IDs 101, 102
    expect(classGroups.get(1)).toEqual([101, 102]);
    // class 2: ID 201
    expect(classGroups.get(2)).toEqual([201]);
    // class 0: ID 1
    expect(classGroups.get(0)).toEqual([1]);
  });
});

describe("LEGACY_RETICLE_TRIPLES", () => {
  it("has length 3 (STRIDE=3 format)", () => {
    expect(LEGACY_RETICLE_TRIPLES).toHaveLength(3);
  });

  it("has expected values", () => {
    expect(LEGACY_RETICLE_TRIPLES).toEqual([7, 8, 9001]);
  });
});

describe("LARGE_POINTS", () => {
  it("has length 60 000 (10 000 points × STRIDE=6)", () => {
    expect(LARGE_POINTS).toHaveLength(60_000);
  });

  it("matches makeStride6Points(10000) output", () => {
    expect(LARGE_POINTS).toEqual(makeStride6Points(10_000));
  });

  it("starts with expected defectId = 1", () => {
    expect(LARGE_POINTS[2]).toBe(1);
  });
});
