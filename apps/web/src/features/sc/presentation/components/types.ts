export interface DieStackPoint {
  id: string;
  dieX: number;
  dieY: number;
  roughBin: number;
  classNumber: number | null;
  defectId: string;
}

export interface HighlightDefect {
  defectId: number;
  waferX: number;
  waferY: number;
  dieX: number;
  dieY: number;
  reticleX: number;
  reticleY: number;
}
