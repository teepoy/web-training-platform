/** Minimal point type for pure-render map components (no selection / interaction). */
export interface SimpleMapPoint {
  x: number;
  y: number;
  id: number;
  label: string;
  hasImageFlag: boolean;
  isSelectedFlag: boolean;
}
