import type { ScMapRegion } from "./types";

export const SC_MAP_PROJECTION_OVERSCAN_RATIO = 0.2;

export interface ScMapRenderViewport {
  visibleRegion: ScMapRegion;
  renderRegion: ScMapRegion;
  renderWidth: number;
  renderHeight: number;
  offsetX: number;
  offsetY: number;
}

export function fitMapRegionToViewport(
  region: ScMapRegion,
  width: number,
  height: number,
): ScMapRegion {
  if (!(region.w > 0) || !(region.h > 0) || !(width > 0) || !(height > 0)) {
    throw new Error("Map region and viewport dimensions must be positive");
  }
  const viewportAspect = width / height;
  const regionAspect = region.w / region.h;
  if (regionAspect < viewportAspect) {
    const fittedWidth = region.h * viewportAspect;
    return {
      x: region.x - (fittedWidth - region.w) / 2,
      y: region.y,
      w: fittedWidth,
      h: region.h,
    };
  }
  const fittedHeight = region.w / viewportAspect;
  return {
    x: region.x,
    y: region.y - (fittedHeight - region.h) / 2,
    w: region.w,
    h: fittedHeight,
  };
}

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

export function createMapRenderViewport(
  region: ScMapRegion,
  width: number,
  height: number,
  ratio = SC_MAP_PROJECTION_OVERSCAN_RATIO,
): ScMapRenderViewport {
  const visibleRegion = fitMapRegionToViewport(region, width, height);
  const renderRegion = overscanMapRegion(visibleRegion, ratio);
  const renderWidth = width * (renderRegion.w / visibleRegion.w);
  const renderHeight = height * (renderRegion.h / visibleRegion.h);
  return {
    visibleRegion,
    renderRegion,
    renderWidth,
    renderHeight,
    offsetX: (renderWidth - width) / 2,
    offsetY: (renderHeight - height) / 2,
  };
}
