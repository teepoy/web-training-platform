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

export interface ScSampleTableDisplayRow {
  row_key: string;
  sample_id?: string | null;
  defect_id: string;
  rough_bin: number;
  class_number: number;
  images: number;
  test_id: number;
  wafer_x: number;
  wafer_y: number;
  index_x: number;
  index_y: number;
  adder: number;
  cluster_id?: number | null;
  die_x: number;
  die_y: number;
  reticle_x: number;
  reticle_y: number;
  size_x: number;
  size_y: number;
  size_d: number;
  area: number;
  final_bin: number;
  manual_bin: number;
  kill_ratio?: number | null;
  source_dataset_id?: string | null;
  source_sample_id?: string | null;
  annotation_label?: string | null;
  prediction_label?: string | null;
  prediction_confidence?: number | null;
  repeater_id?: number | null;
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
