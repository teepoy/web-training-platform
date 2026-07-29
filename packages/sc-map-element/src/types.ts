export interface ScMapRegion {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface ScMapBounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

export interface ScMapViewport {
  width: number;
  height: number;
  dpr: number;
  centerX: number;
  centerY: number;
  dataRangeNm: number;
  zoom: ScMapRegion | null;
  dataBounds: ScMapBounds | null;
}

export interface ScMapData {
  points: Float32Array;
  colorMap: Record<string, string>;
  showImageMarkers: boolean;
  defectSize: number;
}
