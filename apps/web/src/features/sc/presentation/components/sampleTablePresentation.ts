import type { ScDataColumn } from "@/features/sc/domain/workbenchDataSource";
import type { ScSampleTableDisplayRow } from "@/features/sc/domain/workbenchInteraction";
import { SC_RECLASSIFY_TABLE_COLUMNS, SC_SAMPLE_TABLE_COLUMNS } from "./scSampleTableColumns";

export interface ScSampleTablePresentationRow
  extends Partial<ScSampleTableDisplayRow>, Record<string, unknown> {
  row_key: string;
  defect_id: string;
  _isHydrated?: boolean;
}

export interface ScSampleTablePresentationColumn {
  key: string;
  title: string;
  width: number;
  filter: "set" | "range" | null;
  render?: (row: ScSampleTablePresentationRow) => string;
}

const knownColumns = new Map<string, ScSampleTablePresentationColumn>(
  [...SC_SAMPLE_TABLE_COLUMNS, ...SC_RECLASSIFY_TABLE_COLUMNS].map((column) => [
    String(column.key),
    column as ScSampleTablePresentationColumn,
  ]),
);
const reclassifyColumnKeys = new Set(
  SC_RECLASSIFY_TABLE_COLUMNS.map((column) => String(column.key)),
);

function dynamicColumn(column: ScDataColumn): ScSampleTablePresentationColumn {
  const arrowType = column.arrowType.toLowerCase();
  const numeric = /(^|[^a-z])(u?int|float|double|decimal)/.test(arrowType);
  const scalar =
    numeric ||
    arrowType.includes("bool") ||
    arrowType.includes("utf8") ||
    arrowType.includes("string") ||
    arrowType.includes("date") ||
    arrowType.includes("time");
  return {
    key: column.name,
    title: column.name,
    width: Math.max(120, Math.min(240, column.name.length * 9 + 44)),
    filter: numeric ? "range" : scalar ? "set" : null,
  };
}

export function sampleTablePresentationColumns(
  sourceColumns: readonly ScDataColumn[] | null,
  showReclassifyColumns: boolean,
): ScSampleTablePresentationColumn[] {
  if (sourceColumns === null) {
    return showReclassifyColumns
      ? ([
          ...SC_SAMPLE_TABLE_COLUMNS,
          ...SC_RECLASSIFY_TABLE_COLUMNS,
        ] as ScSampleTablePresentationColumn[])
      : (SC_SAMPLE_TABLE_COLUMNS as ScSampleTablePresentationColumn[]);
  }
  return sourceColumns
    .filter((column) => showReclassifyColumns || !reclassifyColumnKeys.has(column.name))
    .map((column) => knownColumns.get(column.name) ?? dynamicColumn(column));
}

export function normalizeSampleTableFilterValue(
  field: string,
  value: string | number,
): string | number {
  if (field !== "defect_id") return value;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : value;
}

export function sampleTableRowDefectId(
  row: ScSampleTablePresentationRow | undefined,
): number | null {
  if (!row) return null;
  const id = Number(row.defect_id);
  return Number.isFinite(id) ? id : null;
}

export function sampleTableRowKey(row: ScSampleTablePresentationRow | undefined): string | null {
  if (!row) return null;
  const key = String(row.row_key ?? "").trim();
  return key.length > 0 ? key : null;
}

export function renderSampleTableCell(
  definition: ScSampleTablePresentationColumn,
  row: ScSampleTablePresentationRow | undefined,
): string {
  if (!row) return "";
  if (definition.key !== "defect_id" && !row._isHydrated) return "";
  if (definition.render) return definition.render(row);
  const value = row[definition.key];
  if (value == null || value === "") return "-";
  if (value instanceof Uint8Array) return `[${value.byteLength} bytes]`;
  if (typeof value === "object") {
    return JSON.stringify(value, (_key, item: unknown) =>
      typeof item === "bigint" ? item.toString() : item,
    );
  }
  return String(value);
}
