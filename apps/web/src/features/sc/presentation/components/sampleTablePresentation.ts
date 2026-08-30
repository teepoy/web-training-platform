import type { ScDataColumn } from "@/features/sc/domain/workbenchDataSource";
import type { ScSampleTableDisplayRow } from "@/features/sc/domain/workbenchInteraction";
import { formatScClassNumber } from "@/features/sc/domain/classNumberDisplay";
import { scSampleTableColumns, type ScNumericRangeControl } from "./scSampleTableColumns";

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
  numericRange: ScNumericRangeControl | null;
  render?: (row: ScSampleTablePresentationRow) => string;
}

function formattedValue(
  key: string,
  format: "plain" | "integer" | "fixed_3",
  row: ScSampleTablePresentationRow,
): string {
  const value = row[key];
  if (key === "class_number") return formatScClassNumber(value);
  if (format === "integer") return String(Number(value));
  if (format === "fixed_3") {
    const numeric = Number(value);
    return value != null && Number.isFinite(numeric) ? numeric.toFixed(3) : "-";
  }
  return String(value);
}

export function sampleTablePresentationColumns(
  sourceColumns: readonly ScDataColumn[] | null,
  showReclassifyColumns: boolean,
): ScSampleTablePresentationColumn[] {
  if (sourceColumns === null) return [];
  return scSampleTableColumns(sourceColumns, showReclassifyColumns).map(
    ({ format, ...column }) => ({
      ...column,
      ...(format === "plain" && column.key !== "class_number"
        ? {}
        : {
            render: (row: ScSampleTablePresentationRow) => formattedValue(column.key, format, row),
          }),
    }),
  );
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
