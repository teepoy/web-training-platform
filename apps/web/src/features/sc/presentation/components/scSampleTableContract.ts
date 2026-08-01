import type { ScSampleTableFilter, ScSampleTableSort } from "@/features/sc/domain/sampleTable";
import type { ScTableSelectionConstraint } from "@/features/sc/domain/workbenchDataSource";
import type { ScSampleTableDataSource } from "@/features/sc/domain/workbenchInteraction";

export interface ScSampleTableBaseProps {
  loading?: boolean;
  selection?: ScTableSelectionConstraint;
  filter?: ScSampleTableFilter;
  sort?: ScSampleTableSort | null;
  showReclassifyColumns?: boolean;
  enableSelection?: boolean;
}

export interface ScSampleTableProps extends ScSampleTableBaseProps {
  dataSource?: ScSampleTableDataSource;
  defectIds?: string[];
  total?: number;
  reticleXDieCount?: number;
  reticleYDieCount?: number;
  reticleXDieShift?: number;
  reticleYDieShift?: number;
}

export interface ScSampleTableEmits {
  (e: "selection-change", selection: ScTableSelectionConstraint): void;
  (e: "filter-change", filter: ScSampleTableFilter): void;
  (e: "sort-change", sort: { field: string; direction: "asc" | "desc" | null }): void;
}
