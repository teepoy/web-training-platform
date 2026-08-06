export {
  clampRegionToBounds,
  defineScMapElement,
  normalizeWheelDelta,
  pointInPolygon,
  SC_MAP_WHEEL_ZOOM_COMMIT_DELAY_MS,
  SC_MAP_WHEEL_ZOOM_SENSITIVITY,
  SC_MAP_TAG_NAME,
  ScMapElement,
  zoomRegionAroundPoint,
} from "./sc-map-element";
export type {
  ScMapGeometry,
  ScMapErrorDetail,
  ScMapInteractionMode,
  ScMapLassoSelection,
  ScMapMode,
  ScMapPoint,
  ScMapProgress,
} from "./sc-map-element";
export type { ScMapBounds, ScMapData, ScMapRegion, ScMapViewport } from "./types";
export { encodeLegendColorMap, encodeLegendKey, normalizeLegendKey } from "./legend-key-codec";
export { copyMapArrowChunksForTransfer } from "./map-arrow-client";
export { overscanMapRegion, SC_MAP_PROJECTION_OVERSCAN_RATIO } from "./map-projection";
