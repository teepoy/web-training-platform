import { computed, type Ref } from "vue";
import type { Filter, View } from "@perspective-dev/client";
import type { ScSampleTableFilter } from "@/features/sc/domain/sampleTable";
import type {
  ScSampleTableDataSource,
  ScSampleTableDisplayRow,
} from "@/features/sc/domain/workbenchInteraction";

const TABLE_TO_PERSPECTIVE_FIELD: Record<string, string> = {
  class_number: "class_number",
  annotation_label: "annotation_label",
  prediction_label: "prediction_label",
};

function perspectiveField(field: string): string {
  return TABLE_TO_PERSPECTIVE_FIELD[field] ?? field;
}

function filtersFromSampleTable(filter: ScSampleTableFilter | undefined, omitField?: string) {
  const out: Array<[string, string, unknown]> = [];
  for (const [field, raw] of Object.entries(filter ?? {})) {
    if (field === omitField) continue;
    const col = perspectiveField(field);
    const sf = raw as {
      filterType: string;
      values?: Array<string | number>;
      type?: string;
      filter?: number;
      filterTo?: number;
    };
    if (sf.filterType === "set" && sf.values?.length) {
      out.push([col, "in", sf.values]);
    }
    if (
      sf.filterType === "number" &&
      sf.type === "inRange" &&
      typeof sf.filter === "number" &&
      typeof sf.filterTo === "number"
    ) {
      out.push([col, ">=", sf.filter], [col, "<=", sf.filterTo]);
    }
  }
  return out;
}

function numericSearchFilter(
  field: string,
  search: string,
): Array<[string, string, unknown]> | null {
  const trimmed = search.trim();
  if (!trimmed) return [];
  const values = trimmed
    .split(",")
    .map((part) => Number(part.trim()))
    .filter(Number.isFinite);
  if (values.length === 0) return null;
  return values.length === 1 ? [[field, "==", values[0]]] : [[field, "in", values]];
}

function asRecord(data: unknown): Record<string, unknown[]> {
  return data as Record<string, unknown[]>;
}

function rowAt<T>(data: Record<string, unknown[]>, key: string, index: number, fallback: T): T {
  return (data[key]?.[index] as T | undefined) ?? fallback;
}

function makeRows(data: Record<string, unknown[]>): ScSampleTableDisplayRow[] {
  const defectIds = data.defect_id ?? [];
  const rows: ScSampleTableDisplayRow[] = [];
  for (let i = 0; i < defectIds.length; i += 1) {
    rows.push({
      defect_id: String(defectIds[i] ?? ""),
      rough_bin: rowAt(data, "rough_bin", i, 0),
      class_number: rowAt(data, "class_number", i, 0),
      images: rowAt(data, "images", i, 0),
      test_id: rowAt(data, "test_id", i, 0),
      wafer_x: rowAt(data, "wafer_x", i, 0),
      wafer_y: rowAt(data, "wafer_y", i, 0),
      index_x: rowAt(data, "index_x", i, 0),
      index_y: rowAt(data, "index_y", i, 0),
      adder: rowAt(data, "adder", i, 0),
      cluster_id: rowAt(data, "cluster_id", i, null),
      die_x: rowAt(data, "die_x", i, 0),
      die_y: rowAt(data, "die_y", i, 0),
      reticle_x: rowAt(data, "reticle_x", i, 0),
      reticle_y: rowAt(data, "reticle_y", i, 0),
      size_x: rowAt(data, "size_x", i, 0),
      size_y: rowAt(data, "size_y", i, 0),
      size_d: rowAt(data, "size_d", i, 0),
      area: rowAt(data, "area", i, 0),
      final_bin: rowAt(data, "final_bin", i, 0),
      manual_bin: rowAt(data, "manual_bin", i, 0),
      kill_ratio: rowAt(data, "kill_ratio", i, null),
      annotation_label: rowAt(data, "annotation_label", i, null),
      prediction_label: rowAt(data, "prediction_label", i, null),
      prediction_confidence: rowAt(data, "prediction_confidence", i, null),
    });
  }
  return rows;
}

export function usePerspectiveSampleTableDataSource(
  table: Ref<import("@perspective-dev/client").Table | null>,
  scopeKey: Ref<string>,
  baseFilters?: Ref<Filter[]>,
  activeView?: Ref<View | null>,
  activeViewVersion?: Ref<number>,
) {
  return computed<ScSampleTableDataSource | undefined>(() => {
    const tbl = table.value;
    if (!tbl) return undefined;
    const baseFilterKey = JSON.stringify(baseFilters?.value ?? []);
    const viewKey = activeView?.value ? `view:${activeViewVersion?.value ?? 0}` : "table";
    return {
      scopeKey: `${scopeKey.value}:${baseFilterKey}:${viewKey}`,
      async loadRows(query) {
        const prebuiltView = activeView?.value;
        if (prebuiltView) {
          const total = await prebuiltView.num_rows();
          const offset = Number.parseInt(query.anchor, 10) || 0;
          const endRow = Math.min(offset + query.limit, total);
          if (endRow <= offset) return { items: [], total, nextAnchor: null };
          const data = asRecord(
            await prebuiltView.to_columns({ start_row: offset, end_row: endRow }),
          );
          return {
            items: makeRows(data),
            total,
            nextAnchor: endRow < total ? String(endRow) : null,
          };
        }

        const filter = [...(baseFilters?.value ?? []), ...filtersFromSampleTable(query.filter)];
        const sort = query.sort?.direction
          ? ([[perspectiveField(query.sort.field), query.sort.direction]] as [string, string][])
          : undefined;
        const v: View = await tbl.view({
          filter: filter.length ? filter : undefined,
          sort,
        } as never);
        try {
          const total = await v.num_rows();
          const offset = Number.parseInt(query.anchor, 10) || 0;
          const endRow = Math.min(offset + query.limit, total);
          if (endRow <= offset) return { items: [], total, nextAnchor: null };
          const data = asRecord(await v.to_columns({ start_row: offset, end_row: endRow }));
          return {
            items: makeRows(data),
            total,
            nextAnchor: endRow < total ? String(endRow) : null,
          };
        } finally {
          try {
            v.delete();
          } catch {
            /* best effort */
          }
        }
      },
      async loadDistinctValues(query) {
        const field = perspectiveField(query.field);
        const searchFilters = numericSearchFilter(field, query.search);
        if (searchFilters === null) return [];
        const filter = [
          ...(baseFilters?.value ?? []),
          ...filtersFromSampleTable(query.filter, query.field),
          ...searchFilters,
        ];
        const v: View = await tbl.view({
          columns: [field],
          group_by: [field],
          aggregates: { [field]: "count" },
          filter: filter.length ? filter : undefined,
        } as never);
        try {
          const total = await v.num_rows();
          if (total === 0) return [];
          const data = asRecord(
            await v.to_columns({ start_row: 0, end_row: Math.min(total, query.limit) }),
          );
          const rowPaths = data.__ROW_PATH__ as unknown[][] | undefined;
          return (rowPaths ?? [])
            .map((path) => path?.[0])
            .filter(
              (value): value is string | number =>
                typeof value === "string" || typeof value === "number",
            );
        } finally {
          try {
            v.delete();
          } catch {
            /* best effort */
          }
        }
      },
    };
  });
}
