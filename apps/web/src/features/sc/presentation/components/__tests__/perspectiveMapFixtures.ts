/**
 * Factory helpers for Perspective-binned map STRIDE=6 test/story data.
 *
 * Perspective STRIDE=6 point format: [x, y, legendValue, mapInSelection, hasImages, galleryInSelection]
 *
 * - x/y: coordinates in nm
 * - legendValue: numeric legend category
 * - mapInSelection: 0 or 1
 * - hasImages: 0 or 1
 * - galleryInSelection: 0 or 1
 */

import type { PerspectiveMapPoint } from "../SimpleMapPoint";
import type { HighlightDefect } from "../types";

const STRIDE = 6;

interface MakePerspectiveOptions {
  count?: number;
  baseX?: number;
  baseY?: number;
  strideX?: number;
  strideY?: number;
  legendValue?: number;
  mapInSelection?: boolean;
  hasImages?: boolean;
  galleryInSelection?: boolean;
}

/**
 * Generate a flat packed array and typed PerspectiveMapPoint[] from STRIDE=6 data.
 *
 * Points are arranged linearly: point[i] at (baseX + i*strideX, baseY + i*strideY).
 * Boolean flags are encoded as 0 or 1 in the packed array.
 */
export function makePerspectiveStride6Points(opts: MakePerspectiveOptions = {}): {
  packed: number[];
  points: PerspectiveMapPoint[];
} {
  const count = opts.count ?? 3;
  const baseX = opts.baseX ?? 100;
  const baseY = opts.baseY ?? 200;
  const strideX = opts.strideX ?? 10;
  const strideY = opts.strideY ?? 10;
  const legendValue = opts.legendValue ?? 0;
  const mapInSelection = opts.mapInSelection ?? false;
  const hasImages = opts.hasImages ?? false;
  const galleryInSelection = opts.galleryInSelection ?? false;

  const packed = new Array<number>(count * STRIDE);
  const points = new Array<PerspectiveMapPoint>(count);

  for (let i = 0; i < count; i++) {
    const offset = i * STRIDE;
    const x = baseX + i * strideX;
    const y = baseY + i * strideY;

    packed[offset] = x;
    packed[offset + 1] = y;
    packed[offset + 2] = legendValue;
    packed[offset + 3] = mapInSelection ? 1 : 0;
    packed[offset + 4] = hasImages ? 1 : 0;
    packed[offset + 5] = galleryInSelection ? 1 : 0;

    points[i] = {
      x,
      y,
      label: String(legendValue),
      mapInSelection,
      hasImages,
      galleryInSelection,
    };
  }

  return { packed, points };
}

interface MakeHighlightDefectsOptions {
  startId?: number;
}

/**
 * Generate an array of HighlightDefect with auto-incrementing coordinates.
 *
 * Default starting values:
 *   waferX=1000, waferY=2000, dieX=100, dieY=200, reticleX=10, reticleY=20
 * Each subsequent defect increments coordinates by 10.
 */
export function makeHighlightDefects(
  count: number,
  opts: MakeHighlightDefectsOptions = {},
): HighlightDefect[] {
  const startId = opts.startId ?? 1;
  const result = new Array<HighlightDefect>(count);

  for (let i = 0; i < count; i++) {
    result[i] = {
      defectId: startId + i,
      waferX: 1000 + i * 10,
      waferY: 2000 + i * 10,
      dieX: 100 + i * 10,
      dieY: 200 + i * 10,
      reticleX: 10 + i * 10,
      reticleY: 20 + i * 10,
    };
  }

  return result;
}
