/** Pre-computed data bounds for a die stack map viewport. */

export interface DataBounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

/**
 * Compute data bounds from a flat number array `[dieX, dieY, id, ...]`.
 */
export function computeBoundsFromFlatArray(pts: Array<number>): DataBounds {
  if (!pts || pts.length === 0) return { minX: 0, maxX: 10, minY: 0, maxY: 10 };

  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;

  for (let i = 0; i < pts.length; i += 3) {
    if (pts[i] < minX) minX = pts[i];
    if (pts[i] > maxX) maxX = pts[i];
    if (pts[i + 1] < minY) minY = pts[i + 1];
    if (pts[i + 1] > maxY) maxY = pts[i + 1];
  }

  const spanX = maxX - minX || 2;
  const spanY = maxY - minY || 2;
  const padX = Math.max(1, spanX * 0.1);
  const padY = Math.max(1, spanY * 0.1);

  return {
    minX: Math.floor(minX - padX),
    maxX: Math.ceil(maxX + padX),
    minY: Math.floor(minY - padY),
    maxY: Math.ceil(maxY + padY),
  };
}
