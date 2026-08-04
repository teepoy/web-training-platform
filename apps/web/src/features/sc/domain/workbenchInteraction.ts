import type { ScSampleTableRow } from "@/generated/orval/models/scSampleTableRow";
import type { ScSampleTableRowsRequest } from "@/generated/orval/models/scSampleTableRowsRequest";
import type { ScSampleTableFilter, ScSampleTableSort } from "@/features/sc/domain/sampleTable";
import type { ReticleMapOptions } from "@/features/sc/application/reticleMapOptions";
import type { ScDataColumn } from "@/features/sc/domain/workbenchDataSource";

export type ScLegendSource = "class" | "bin" | "annotation" | "prediction" | "final_class";
export type ScMapSelectionMode = "include" | "exclude";
export type ScSelectionSource = "sample-table" | "blink-table";

export interface ScMapRegion {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface ScSelectionAction {
  source: ScSelectionSource;
  ids: string[];
  mode: "replace" | "add" | "toggle";
}

export interface ScSampleTableDisplayRow extends ScSampleTableRow {
  annotation_label?: string | null;
  prediction_label?: string | null;
  prediction_confidence?: number | null;
}

export interface ScSampleTableRowsQuery {
  defectIds: string[];
  anchor: string;
  limit: number;
  filter?: ScSampleTableFilter;
  sort?: ScSampleTableSort | null;
  reticleOptions?: ReticleMapOptions;
  signal?: AbortSignal;
}

export interface ScSampleTableRowsPage {
  items: ScSampleTableDisplayRow[];
  total: number;
  nextAnchor: string | null;
}

export interface ScSampleTableDistinctValuesQuery {
  field: string;
  search: string;
  limit: number;
  filter?: ScSampleTableFilter;
  sort?: ScSampleTableSort | null;
}

export interface ScSampleTableDataSource {
  scopeKey: string;
  loadColumns?: () => Promise<ScDataColumn[]>;
  loadRows: (query: ScSampleTableRowsQuery) => Promise<ScSampleTableRowsPage>;
  loadDistinctValues?: (query: ScSampleTableDistinctValuesQuery) => Promise<Array<string | number>>;
}

export function buildScSampleTableRowsRequest(
  query: ScSampleTableRowsQuery,
): ScSampleTableRowsRequest {
  const payload: ScSampleTableRowsRequest = {
    anchor: query.anchor,
    limit: query.limit,
  };
  if (query.defectIds.length > 0) {
    payload.defect_ids = query.defectIds;
  }
  if (query.filter && Object.keys(query.filter).length > 0) {
    payload.filter = query.filter;
  }
  if (query.sort?.direction) {
    payload.sort = query.sort;
  }
  if (query.reticleOptions) {
    payload.reticle_x_die_count = query.reticleOptions.xDieCount;
    payload.reticle_y_die_count = query.reticleOptions.yDieCount;
    payload.reticle_x_die_shift = query.reticleOptions.xDieShift;
    payload.reticle_y_die_shift = query.reticleOptions.yDieShift;
  }
  return payload;
}
