import type { ScSampleTableRowsRequestFilterAnyOf } from "@/generated/orval/models/scSampleTableRowsRequestFilterAnyOf";

export type ScSampleTableFilter = ScSampleTableRowsRequestFilterAnyOf;

export interface ScSampleTableSort {
  field: string;
  direction: "asc" | "desc";
}
