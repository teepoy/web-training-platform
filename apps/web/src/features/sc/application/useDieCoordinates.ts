/**
 * Mathematical floor modulus — always returns a non-negative result.
 *
 * In JavaScript, `%` is a remainder operator that preserves the sign of the
 * dividend, so `-5 % 10 === -5`.  `floorMod` wraps the result into `[0, n)`,
 * which is the correct behaviour for coordinate arithmetic where negative
 * offsets must wrap around to the positive range.
 *
 * @param a - Dividend (may be negative).
 * @param n - Divisor (must be positive).
 * @returns `((a % n) + n) % n` — always in `[0, n)`.
 */
export function floorMod(a: number, n: number): number {
  return ((a % n) + n) % n;
}

/**
 * Compute a die-level coordinate from a raw wafer coordinate.
 *
 * Wafer coordinates are large absolute numbers (origin ~150M, wafer_x/y
 * ~0-300M).  Subtracting the origin and applying `floorMod` against the die
 * size yields a compact die-relative index suitable for scatter-plot axes.
 *
 * @param waferCoord - Raw absolute wafer coordinate (e.g. `wafer_x` or `wafer_y`).
 * @param origin     - Reference origin for this wafer (e.g. `die_origin_x`).
 * @param dieSize    - Die width or height for this product.
 * @returns Non-negative die-relative coordinate.
 */
export function computeDieCoord(
  waferCoord: number,
  origin: number,
  dieSize: number,
): number {
  return floorMod(waferCoord - origin, dieSize);
}
