import type { Table } from "apache-arrow";
import type { ScSampleTableFilter, ScSampleTableSort } from "./sampleTable";
import type {
  ScSampleTableDistinctValuesQuery,
  ScSampleTableRowsPage,
  ScSampleTableRowsQuery,
} from "./workbenchInteraction";
import type { ReticleMapOptions } from "@/features/sc/application/reticleMapOptions";
import type { ScMapLassoSelection } from "@platform/sc-map-element";

export type ScDataScalar = boolean | number | string | null;
export type ScDataParameter = ScDataScalar | boolean[] | number[] | string[];
export type ScDataFilter = [field: string, operator: string, value: unknown];

export interface ScReticleProjection {
  options: ReticleMapOptions;
  dieSizeX: number;
  dieSizeY: number;
}

export interface ScDataQueryContext {
  filters?: readonly ScDataFilter[];
  reticle?: ScReticleProjection;
}

export interface ScMapDataQuery extends ScDataQueryContext {
  legendColumn: string;
}

export type ScTableSelectionConstraint =
  | { kind: "ids"; ids: readonly number[] }
  | { kind: "all"; excludedIds: readonly number[] };

export interface ScGalleryDataQuery extends ScDataQueryContext {
  mode: "patch" | "review";
  offset: number;
  limit: number;
  tableFilter?: ScSampleTableFilter;
  tableSort?: ScSampleTableSort | null;
  tableSelection?: ScTableSelectionConstraint;
}

export interface ScAggregateDataQuery extends ScDataQueryContext {
  field: string;
}

export interface ScNumericRangeQuery extends ScDataQueryContext {
  field: string;
}

export interface ScNumericRange {
  min: number;
  max: number;
}

export type ScSelectionConstraint =
  | { kind: "all" }
  | { kind: "ids"; ids: readonly number[] }
  | {
      kind: "rectangle";
      mode: "wafer" | "die" | "reticle";
      x: number;
      y: number;
      width: number;
      height: number;
    }
  | {
      kind: "polygon";
      mode: "wafer" | "die" | "reticle";
      selection: ScMapLassoSelection;
    }
  | { kind: "legend"; field: string; value: string | number | null }
  | { kind: "random"; limit: number; seed: number };

export interface ScSelectionQuery extends ScDataQueryContext {
  constraint: ScSelectionConstraint;
}

export interface ScGalleryPage {
  ipc: Uint8Array | null;
  total: number;
  nextOffset: number | null;
}

export interface ScInvalidation {
  scope: string;
  revision: number;
  changedKinds: readonly string[];
}

export interface ScDataColumn {
  /** Exact field name and Arrow type returned by SELECT * FROM samples LIMIT 0. */
  name: string;
  arrowType: string;
  nullable: boolean;
}

export interface ScWorkbenchDataSource {
  readonly scopeKey: string;
  loadColumns(): Promise<ScDataColumn[]>;
  loadMap(query: ScMapDataQuery): Promise<Uint8Array>;
  loadRows(query: ScSampleTableRowsQuery & ScDataQueryContext): Promise<ScSampleTableRowsPage>;
  loadGallery(query: ScGalleryDataQuery): Promise<ScGalleryPage>;
  loadAggregates(query: ScAggregateDataQuery): Promise<Record<string, number>>;
  loadNumericRange(query: ScNumericRangeQuery): Promise<ScNumericRange | null>;
  loadDistinctValues(
    query: ScSampleTableDistinctValuesQuery & ScDataQueryContext,
  ): Promise<Array<string | number>>;
  resolveSelection(query: ScSelectionQuery): Promise<number[]>;
  subscribeInvalidations(listener: (event: ScInvalidation) => void): () => void;
  close(): void;
}

export interface ScArrowQueryResult {
  table: Table;
  revision: number;
}
