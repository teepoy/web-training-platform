/**
 * Factory helpers for SC map flat STRIDE=6 test/story data.
 *
 * STRIDE=6 point format: [x, y, defectId, classNumber, roughBin, hasReview]
 *
 * - x/y: coordinates in nm
 * - defectId: unique point identifier
 * - classNumber: classification (0 = unknown/no defect, 1+ = specific classes)
 * - roughBin: bin category
 * - hasReview: 0 or 1
 */

/** Number of int32 values per point in the flat array. */
const STRIDE = 6;

/**
 * Generate a flat array of STRIDE=6 wafer map points.
 *
 * Coordinates are deterministic (Fibonacci spiral distribution).
 * IDs ascend sequentially from `startId`.
 * Classes cycle through 0, 1, 2 starting from `classSeed`.
 *
 * @param count  Number of points to generate.
 * @param opts.startId   First defectId (default 1).
 * @param opts.classSeed Rotation offset for class cycling (default 0).
 */
export function makeStride6Points(
  count: number,
  opts?: { startId?: number; classSeed?: number },
): number[] {
  const startId = opts?.startId ?? 1;
  const classSeed = opts?.classSeed ?? 0;
  const total = count * STRIDE;
  const points = new Array<number>(total);

  for (let i = 0; i < count; i++) {
    const offset = i * STRIDE;
    const ratio = (i + 0.5) / Math.max(count, 1);
    const r = Math.sqrt(ratio) * 150_000_000 * 0.98;
    const theta = i * Math.PI * (3 - Math.sqrt(5));
    points[offset] = Math.round(r * Math.cos(theta));       // x
    points[offset + 1] = Math.round(r * Math.sin(theta));   // y
    points[offset + 2] = startId + i;                       // defectId
    points[offset + 3] = (i + classSeed) % 3;               // classNumber
    points[offset + 4] = 0;                                 // roughBin
    points[offset + 5] = 0;                                 // hasReview
  }

  return points;
}

/** Empty points array. */
export const EMPTY_POINTS: number[] = [];

/** Single point (STRIDE=6): x=100, y=200, defectId=1, classNumber=1, roughBin=0, hasReview=0. */
export const SINGLE_POINT: number[] = [100, 200, 1, 1, 0, 0];

/**
 * 4 points with mixed classes:
 *   - class 1 → IDs 101, 102
 *   - class 2 → ID   201
 *   - class 0 → ID     1
 */
export const MIXED_CLASS_POINTS: number[] = [
  // x     y    id  cls bin rev
  100,   200, 101,   1,   0,   0,
  1100, 1200, 102,   1,   0,   0,
  2100, 2200, 201,   2,   0,   0,
  3100, 3200,   1,   0,   0,   0,
];

/**
 * Legacy STRIDE=3 reticle triples for padding tests.
 * Format: [x, y, id]
 */
export const LEGACY_RETICLE_TRIPLES: number[] = [7, 8, 9001];

/**
 * 10 000 points (60 000 ints) generated with deterministic seed.
 * Equivalent to `makeStride6Points(10000)`.
 */
export const LARGE_POINTS: number[] = makeStride6Points(10_000);
