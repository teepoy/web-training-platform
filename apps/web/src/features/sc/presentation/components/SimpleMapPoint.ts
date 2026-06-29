/** Minimal point type for pure-render map components (no selection / interaction). */
export interface SimpleMapPoint {
  x: number;
  y: number;
  id: number;
  label: string;
  hasImageFlag: boolean;
  isSelectedFlag: boolean;
}

/** Point type for Perspective-binned map with 4-pass overlay rendering. */
export interface PerspectiveMapPoint {
  x: number;
  y: number;
  label: string;
  mapInSelection: boolean;
  hasImages: boolean;
  galleryInSelection: boolean;
}
