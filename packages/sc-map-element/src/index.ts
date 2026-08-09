export {
  clampRegionToBounds,
  defineScMapElement,
  normalizeWheelDelta,
  SC_MAP_WHEEL_ZOOM_COMMIT_DELAY_MS,
  SC_MAP_WHEEL_ZOOM_SENSITIVITY,
  SC_MAP_TAG_NAME,
  ScMapElement,
  zoomRegionAroundPoint,
} from "./sc-map-element";
export { combineMapSelectionIds, pointInPolygon } from "./map-selection";
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
export type {
  MapSelectionCommand as ScMapSelectionCommand,
  MapSelectionConstraint as ScMapSelectionConstraint,
  MapSelectionResult as ScMapSelectionResult,
} from "./map-arrow-client";
export {
  createMapRenderViewport,
  fitMapRegionToViewport,
  overscanMapRegion,
  SC_MAP_PROJECTION_OVERSCAN_RATIO,
  type ScMapRenderViewport,
} from "./map-projection";
