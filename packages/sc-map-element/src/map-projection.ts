import type { ScMapRegion } from "./types";

export const SC_MAP_PROJECTION_OVERSCAN_RATIO = 0.2;

export function overscanMapRegion(
  region: ScMapRegion,
  ratio = SC_MAP_PROJECTION_OVERSCAN_RATIO,
): ScMapRegion {
  if (!Number.isFinite(ratio) || ratio < 0) {
    throw new Error(`Invalid map projection overscan ratio: ${ratio}`);
  }
  const overscanX = region.w * ratio;
  const overscanY = region.h * ratio;
  return {
    x: region.x - overscanX,
    y: region.y - overscanY,
    w: region.w + overscanX * 2,
    h: region.h + overscanY * 2,
  };
}
