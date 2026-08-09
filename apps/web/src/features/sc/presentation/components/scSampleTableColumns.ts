import type { ScDataColumn } from "@/features/sc/domain/workbenchDataSource";

export interface ScFilterColumnDefinition {
  key: string;
  title: string;
  filter: "set" | "range";
}

export interface ScSampleTableColumnDefinition {
  key: string;
  title: string;
  width: number;
  filter: "set" | "range" | null;
  format: "plain" | "integer" | "fixed_3";
}

function inferredFilter(column: ScDataColumn): "set" | "range" | null {
  const arrowType = column.arrowType.toLowerCase();
  const numeric = /(^|[^a-z])(u?int|float|double|decimal)/.test(arrowType);
  if (numeric) return "range";
  if (
    arrowType.includes("bool") ||
    arrowType.includes("utf8") ||
    arrowType.includes("string") ||
    arrowType.includes("date") ||
    arrowType.includes("time")
  ) {
    return "set";
  }
  return null;
}

function orderedColumns(columns: readonly ScDataColumn[]): ScDataColumn[] {
  return columns
    .map((column, physicalOrder) => ({ column, physicalOrder }))
    .sort(
      (left, right) =>
        (left.column.presentation?.order ?? Number.MAX_SAFE_INTEGER) -
          (right.column.presentation?.order ?? Number.MAX_SAFE_INTEGER) ||
        left.physicalOrder - right.physicalOrder,
    )
    .map(({ column }) => column);
}

function definition(column: ScDataColumn): ScSampleTableColumnDefinition {
  const presentation = column.presentation;
  return {
    key: column.name,
    title: presentation?.title ?? column.name,
    width: presentation?.width ?? Math.max(120, Math.min(240, column.name.length * 9 + 44)),
    filter: presentation ? presentation.filter : inferredFilter(column),
    format: presentation?.format ?? "plain",
  };
}

export function scSampleTableColumns(
  columns: readonly ScDataColumn[],
  showReclassifyColumns: boolean,
): ScSampleTableColumnDefinition[] {
  return orderedColumns(columns)
    .filter((column) => {
      const visibility = column.presentation?.visibility ?? "default";
      return (
        visibility !== "internal" &&
        visibility !== "filter_only" &&
        (showReclassifyColumns || visibility !== "reclassify")
      );
    })
    .map(definition);
}

export function scGlobalFilterColumns(
  columns: readonly ScDataColumn[],
  showReclassifyColumns: boolean,
): ScFilterColumnDefinition[] {
  return orderedColumns(columns).flatMap((column) => {
    const visibility = column.presentation?.visibility ?? "default";
    if (visibility === "internal" || (!showReclassifyColumns && visibility !== "default")) {
      return [];
    }
    const columnDefinition = definition(column);
    return columnDefinition.filter === null
      ? []
      : [
          {
            key: columnDefinition.key,
            title: columnDefinition.title,
            filter: columnDefinition.filter,
          },
        ];
  });
}
