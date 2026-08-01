export interface DieStackPoint {
  id: string;
  dieX: number;
  dieY: number;
  roughBin: number;
  classNumber: number | null;
  defectId: string;
}

export interface MapPointVisual {
  label: string;
  color: string;
}
