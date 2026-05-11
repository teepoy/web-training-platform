export type BlinkPhase = "A" | "B";

export interface BlinkRow {
  id: string;
  imageA: string;
  imageB: string;
  metadata: Record<string, unknown>;
  cells: Record<string, string>;
}

export interface BlinkColumnDef {
  key: string;
  title: string;
  width?: number;
}

export interface BlinkTableProps {
  rows: BlinkRow[];
  columns: BlinkColumnDef[];
  blinkIntervalMs?: number;
  initialBlinkEnabled?: boolean;
}
