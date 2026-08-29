export type ScSampleTableFilterValue =
  | { filterType: "set"; values: Array<string | number>; exclude?: boolean }
  | { filterType: "number"; type: "inRange"; filter: number; filterTo: number };

export type ScSampleTableFilter = Record<string, ScSampleTableFilterValue>;

export interface ScSampleTableSort {
  field: string;
  direction: "asc" | "desc";
}
