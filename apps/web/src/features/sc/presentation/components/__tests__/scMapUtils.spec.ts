import { describe, it, expect, vi } from "vitest";
import {
  STRIDE,
  classColor,
  parsePoints,
  groupByClass,
  getDefectIdsByClass,
  padStride3to6,
  createRafThrottle,
  buildPointLookup,
  getPackedPointIdsInRegion,
  truncatePoints,
  MAX_RENDERED_POINTS,
} from "../scMapUtils";

describe("STRIDE", () => {
  it("is 6", () => {
    expect(STRIDE).toBe(6);
  });
});

describe("classColor", () => {
  it("returns an hsl string", () => {
    const color = classColor(1);
    expect(color).toMatch(/^hsl\(/);
  });

  it("produces different hues for different class IDs", () => {
    const c1 = classColor(1);
    const c2 = classColor(2);
    expect(c1).not.toBe(c2);
  });
});

describe("parsePoints", () => {
  it("parses a normal STRIDE=6 flat array into ScatterPoint[]", () => {
    const flat = [10, 20, 1001, 3, 1, 1, 30, 40, 1002, 5, 0, 0];
    const points = parsePoints(flat);

    expect(points).toHaveLength(2);

    expect(points[0]).toEqual({
      x: 10,
      y: 20,
      defectId: 1001,
      classNumber: 3,
      roughBin: 1,
      hasReview: true,
    });

    expect(points[1]).toEqual({
      x: 30,
      y: 40,
      defectId: 1002,
      classNumber: 5,
      roughBin: 0,
      hasReview: false,
    });
  });

  it("ignores malformed tail (<6 leftover ints)", () => {
    // 14 ints → 2 full points (12 values), last 2 ints are incomplete tail
    const flat = [10, 20, 1001, 1, 1, 0, 50, 60, 1002, 2, 0, 1, 99, 88];
    const points = parsePoints(flat);

    expect(points).toHaveLength(2);
    expect(points[0].defectId).toBe(1001);
    expect(points[1].defectId).toBe(1002);
  });

  it("returns empty array for empty input", () => {
    expect(parsePoints([])).toEqual([]);
  });

  it("returns empty array when fewer than STRIDE values provided", () => {
    expect(parsePoints([1, 2, 3])).toEqual([]);
  });
});

describe("groupByClass", () => {
  it("groups points by classNumber", () => {
    const points = [
      { x: 1, y: 2, defectId: 101, classNumber: 1, roughBin: 0, hasReview: false },
      { x: 3, y: 4, defectId: 102, classNumber: 2, roughBin: 0, hasReview: false },
      { x: 5, y: 6, defectId: 103, classNumber: 1, roughBin: 0, hasReview: false },
      { x: 7, y: 8, defectId: 104, classNumber: 3, roughBin: 0, hasReview: false },
    ];

    const groups = groupByClass(points);

    expect(groups.size).toBe(3);
    expect(groups.get(1)).toHaveLength(2);
    expect(groups.get(2)).toHaveLength(1);
    expect(groups.get(3)).toHaveLength(1);
    expect(groups.get(1)?.[0].defectId).toBe(101);
    expect(groups.get(1)?.[1].defectId).toBe(103);
  });

  it("returns empty map for empty array", () => {
    const groups = groupByClass([]);
    expect(groups.size).toBe(0);
  });
});

describe("getDefectIdsByClass", () => {
  it("returns defect IDs for a given class", () => {
    const points = [
      { x: 0, y: 0, defectId: 201, classNumber: 1, roughBin: 0, hasReview: false },
      { x: 1, y: 1, defectId: 202, classNumber: 2, roughBin: 0, hasReview: false },
      { x: 2, y: 2, defectId: 203, classNumber: 1, roughBin: 0, hasReview: false },
    ];

    const ids = getDefectIdsByClass(points, 1);
    expect(ids).toEqual([201, 203]);
  });

  it("returns empty array when no points of that class exist", () => {
    const points = [
      { x: 0, y: 0, defectId: 301, classNumber: 5, roughBin: 0, hasReview: false },
    ];

    expect(getDefectIdsByClass(points, 99)).toEqual([]);
  });
});

describe("padStride3to6", () => {
  it("pads [x,y,id] triples to STRIDE=6 tuples with [0,0,0]", () => {
    const triples = [10, 20, 1001, 30, 40, 1002];
    const result = padStride3to6(triples);

    expect(result).toHaveLength(12);
    expect(result).toEqual([10, 20, 1001, 0, 0, 0, 30, 40, 1002, 0, 0, 0]);
  });

  it("ignores trailing incomplete triple", () => {
    const triples = [10, 20, 1001, 30];
    const result = padStride3to6(triples);

    expect(result).toHaveLength(6);
    expect(result).toEqual([10, 20, 1001, 0, 0, 0]);
  });

  it("returns empty array for empty input", () => {
    expect(padStride3to6([])).toEqual([]);
  });

  it("returns empty array when fewer than 3 values provided", () => {
    expect(padStride3to6([1, 2])).toEqual([]);
  });
});

describe("MAX_RENDERED_POINTS", () => {
  it("is 50000", () => {
    expect(MAX_RENDERED_POINTS).toBe(50000);
  });
});

describe("getPackedPointIdsInRegion", () => {
  it("returns only points inside the inclusive box", () => {
    const points = [
      10, 20, 101, 1, 0, 0,
      30, 40, 102, 1, 0, 0,
      50, 60, 103, 1, 0, 0,
    ];
    expect(
      getPackedPointIdsInRegion(points, { x: 10, y: 20, w: 20, h: 20 }),
    ).toEqual([101, 102]);
  });
});

describe("createRafThrottle", () => {
  it("returns a function", () => {
    const schedule = createRafThrottle();
    expect(schedule).toBeInstanceOf(Function);
  });

  it("does not invoke callback synchronously", () => {
    const fn = vi.fn();
    const schedule = createRafThrottle();
    schedule(fn);
    expect(fn).not.toHaveBeenCalled();
  });

  it("coalesces multiple calls — first callback runs, subsequent are skipped", () => {
    const fn1 = vi.fn();

    const state: { queued: (() => void) | null } = { queued: null };
    const rafSpy = vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => {
      state.queued = cb as () => void;
      return 1;
    });

    try {
      const schedule = createRafThrottle();
      schedule(fn1);
      schedule(vi.fn());

      expect(fn1).not.toHaveBeenCalled();

      // Simulate the rAF firing — fn1 runs because it was scheduled first
      state.queued?.();
      expect(fn1).toHaveBeenCalledTimes(1);

      // After rAF fires, a new callback can be scheduled
      const fn3 = vi.fn();
      schedule(fn3);
      state.queued?.();
      expect(fn3).toHaveBeenCalledTimes(1);
    } finally {
      rafSpy.mockRestore();
    }
  });
});

describe("buildPointLookup", () => {
  it("returns a Map<defectId, ScatterPoint> for O(1) lookups", () => {
    const points = [
      { x: 10, y: 20, defectId: 1001, classNumber: 1, roughBin: 0, hasReview: false },
      { x: 30, y: 40, defectId: 1002, classNumber: 2, roughBin: 0, hasReview: true },
      { x: 50, y: 60, defectId: 1003, classNumber: 1, roughBin: 1, hasReview: false },
    ];

    const lookup = buildPointLookup(points);

    expect(lookup.size).toBe(3);
    expect(lookup.get(1001)).toEqual(points[0]);
    expect(lookup.get(1002)).toEqual(points[1]);
    expect(lookup.get(1003)).toEqual(points[2]);
    expect(lookup.get(9999)).toBeUndefined();
  });

  it("returns empty map for empty input", () => {
    const lookup = buildPointLookup([]);
    expect(lookup.size).toBe(0);
  });

  it("last-write-wins for duplicate defectId", () => {
    const points = [
      { x: 1, y: 1, defectId: 10, classNumber: 0, roughBin: 0, hasReview: false },
      { x: 2, y: 2, defectId: 10, classNumber: 1, roughBin: 0, hasReview: false },
    ];

    const lookup = buildPointLookup(points);
    expect(lookup.size).toBe(1);
    expect(lookup.get(10)?.x).toBe(2);
  });
});

describe("truncatePoints", () => {
  it("truncates when point count exceeds max", () => {
    const flat: number[] = [];
    for (let i = 0; i < 10; i++) {
      flat.push(i, i + 1, i + 2, 0, 0, 0);
    }
    expect(flat.length).toBe(60); // 10 points

    const { truncated, wasTruncated } = truncatePoints(flat, 3);
    expect(wasTruncated).toBe(true);
    expect(truncated.length).toBe(18); // 3 points × STRIDE=6
    expect(truncated[0]).toBe(0);
  });

  it("returns same reference when under max", () => {
    const flat = [0, 1, 2, 0, 0, 0];
    const { truncated, wasTruncated } = truncatePoints(flat, 10);
    expect(wasTruncated).toBe(false);
    expect(truncated).toBe(flat);
  });

  it("returns same reference when exactly at max", () => {
    const flat: number[] = [];
    for (let i = 0; i < 5; i++) {
      flat.push(i, i + 1, i + 2, 0, 0, 0);
    }
    // 5 points = 30 ints
    const { truncated, wasTruncated } = truncatePoints(flat, 5);
    expect(wasTruncated).toBe(false);
    expect(truncated).toBe(flat);
  });

  it("returns empty array when max is 0 and input is non-empty", () => {
    const flat = [0, 1, 2, 0, 0, 0];
    const { truncated, wasTruncated } = truncatePoints(flat, 0);
    expect(wasTruncated).toBe(true);
    expect(truncated).toHaveLength(0);
  });
});
