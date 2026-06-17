/**
 * scMapUtils — shared pure helpers for wafer map scatter-point data.
 *
 * Extracted from ScWaferMap.vue to support testing and reuse.
 * All functions are stateless; no Canvas, DOM, or Vue dependencies.
 */

export const STRIDE = 6;
export const MAX_RENDERED_POINTS = 50000;

const GOLDEN_RATIO_CONJUGATE = 0.618033988749895;

export interface ScatterPoint {
  x: number;
  y: number;
  defectId: number;
  classNumber: number;
  roughBin: number;
  hasReview: boolean;
}

export type LegendColorSource = "class" | "bin" | "annotation" | "prediction";

const STRING_COLOR_MULTIPLIER = 31;
const MISSING_LEGEND_COLORS = new Set(["__unlabeled__", "__no_prediction__"]);

export function stringColor(value: string): string {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * STRING_COLOR_MULTIPLIER + value.charCodeAt(i)) >>> 0;
  }
  return classColor(hash);
}

/**
 * Map a numeric class ID to a deterministic HSL color string.
 */
export function classColor(classId: number): string {
  const hue = ((classId * GOLDEN_RATIO_CONJUGATE * 360) % 360 + 360) % 360;
  return `hsl(${hue}, 65%, 50%)`;
}

/**
 * Parse a flat int32 array (STRIDE=6 per point) into ScatterPoint[].
 * Ignores trailing values that don't form a complete point.
 */
export function parsePoints(flat: number[]): ScatterPoint[] {
  const count = Math.floor(flat.length / STRIDE);
  const pts: ScatterPoint[] = new Array(count);

  for (let i = 0, pi = 0; pi < count; i += STRIDE, pi++) {
    pts[pi] = {
      x: flat[i],
      y: flat[i + 1],
      defectId: flat[i + 2],
      classNumber: flat[i + 3],
      roughBin: flat[i + 4],
      hasReview: flat[i + 5] !== 0,
    };
  }

  return pts;
}

/**
 * Group scatter points by their classNumber.
 */
export function groupByClass(points: ScatterPoint[]): Map<number, ScatterPoint[]> {
  const groups = new Map<number, ScatterPoint[]>();

  for (const p of points) {
    const cn = p.classNumber;
    let group = groups.get(cn);
    if (!group) {
      group = [];
      groups.set(cn, group);
    }
    group.push(p);
  }

  return groups;
}

/**
 * Extract defect IDs for all points belonging to a given class number.
 */
export function getDefectIdsByClass(points: ScatterPoint[], classId: number): number[] {
  return points.filter((p) => p.classNumber === classId).map((p) => p.defectId);
}

/**
 * Group scatter points by their roughBin.
 */
export function groupByBin(points: ScatterPoint[]): Map<number, ScatterPoint[]> {
  const groups = new Map<number, ScatterPoint[]>();

  for (const p of points) {
    const bin = p.roughBin;
    let group = groups.get(bin);
    if (!group) {
      group = [];
      groups.set(bin, group);
    }
    group.push(p);
  }

  return groups;
}

/**
 * Extract defect IDs for all points belonging to a given rough bin.
 */
export function getDefectIdsByBin(points: ScatterPoint[], bin: number): number[] {
  return points.filter((p) => p.roughBin === bin).map((p) => p.defectId);
}

export function getPackedPointIdsInRegion(
  points: number[],
  region: { x: number; y: number; w: number; h: number },
): number[] {
  const maxX = region.x + region.w;
  const maxY = region.y + region.h;
  const ids: number[] = [];
  for (let i = 0; i + STRIDE - 1 < points.length; i += STRIDE) {
    const x = points[i];
    const y = points[i + 1];
    if (x >= region.x && x <= maxX && y >= region.y && y <= maxY) {
      ids.push(points[i + 2]);
    }
  }
  return ids;
}

/**
 * Map a rough bin value to a deterministic HSL color.
 */
export function binColor(bin: number): string {
  return classColor(bin);
}

export function legendColor(source: LegendColorSource, rawKey: string): string {
  if (MISSING_LEGEND_COLORS.has(rawKey)) return "#9ca3af";
  const numericKey = Number(rawKey);
  if ((source === "class" || source === "bin") && Number.isFinite(numericKey)) {
    return source === "bin" ? binColor(numericKey) : classColor(numericKey);
  }
  return stringColor(rawKey);
}

/**
 * Pad a flat array of [x, y, defectId] triples to STRIDE=6 tuples
 * by appending [0, 0, 0] to each triple.
 *
 * Ignores trailing values that don't form a complete triple.
 */
export function padStride3to6(triples: number[]): number[] {
  const tripleCount = Math.floor(triples.length / 3);
  const result: number[] = new Array(tripleCount * 6);

  for (let i = 0, out = 0; i < tripleCount; i++, out += 6) {
    const src = i * 3;
    result[out] = triples[src];
    result[out + 1] = triples[src + 1];
    result[out + 2] = triples[src + 2];
    result[out + 3] = 0;
    result[out + 4] = 0;
    result[out + 5] = 0;
  }

  return result;
}

/**
 * Return a requestAnimationFrame-throttled wrapper: only the latest
 * scheduled callback fires per frame, and concurrent calls are no-ops.
 */
export function createRafThrottle(): ((fn: () => void) => void) & { cancel: () => void } {
  let rafId = 0;
  const scheduleDraw = function (fn: () => void) {
    if (rafId) return;
    rafId = requestAnimationFrame(() => {
      rafId = 0;
      fn();
    });
  } as ((fn: () => void) => void) & { cancel: () => void };

  scheduleDraw.cancel = () => {
    if (rafId) {
      cancelAnimationFrame(rafId);
      rafId = 0;
    }
  };

  return scheduleDraw;
}

/**
 * Build an O(1) defectId → ScatterPoint lookup map from a point array.
 */
export function buildPointLookup(points: ScatterPoint[]): Map<number, ScatterPoint> {
  const map = new Map<number, ScatterPoint>();
  for (const p of points) {
    map.set(p.defectId, p);
  }
  return map;
}

/**
 * Build an O(1) defectId → {x, y} coordinate lookup from a packed STRIDE=6 array.
 */
export function buildPackedCoordMap(packed: number[]): Map<number, { x: number; y: number }> {
  const map = new Map<number, { x: number; y: number }>();
  for (let i = 0; i + STRIDE - 1 < packed.length; i += STRIDE) {
    map.set(packed[i + 2], { x: packed[i], y: packed[i + 1] });
  }
  return map;
}

/**
 * Truncate a flat STRIDE=6 points array if it exceeds maxPoints.
 * Returns the truncated array and whether truncation occurred.
 */
export function truncatePoints(
  pts: number[],
  maxPoints: number,
): { truncated: number[]; wasTruncated: boolean } {
  const count = Math.floor(pts.length / STRIDE);
  if (count <= maxPoints) return { truncated: pts, wasTruncated: false };
  return { truncated: pts.slice(0, maxPoints * STRIDE), wasTruncated: true };
}
