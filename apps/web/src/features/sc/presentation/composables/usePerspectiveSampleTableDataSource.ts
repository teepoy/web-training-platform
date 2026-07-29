import { computed, onUnmounted, type Ref } from "vue";
import type { Filter } from "@perspective-dev/client";
import { tableFromIPC } from "apache-arrow";
import type {
  ScSampleTableDataSource,
  ScSampleTableDisplayRow,
} from "@/features/sc/domain/workbenchInteraction";
import {
  managePerspectiveTable,
  type ManagedPerspectiveView,
} from "@/features/sc/presentation/composables/managedPerspectiveView";
import {
  buildPerspectiveFilters,
  perspectiveFilterField,
} from "@/features/sc/presentation/composables/perspectiveFilter";
import type { ScPerspectiveTable as Table } from "./perspectiveWorkerClient";
import type { PerspectiveExpressions } from "@/features/sc/presentation/composables/perspectiveReticleExpressions";

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

type ArrowJsonRow = Record<string, unknown>;

function asRecord(data: unknown): Record<string, unknown[]> {
  return data as Record<string, unknown[]>;
}

function arrowRowToRecord(row: unknown): ArrowJsonRow {
  if (row && typeof row === "object" && "toJSON" in row) {
    const toJSON = (row as { toJSON: () => unknown }).toJSON;
    return toJSON.call(row) as ArrowJsonRow;
  }
  return row as ArrowJsonRow;
}

function rowValue<T>(row: ArrowJsonRow, key: string, fallback: T): T {
  return (row[key] as T | undefined) ?? fallback;
}

function makeRows(rows: ArrowJsonRow[]): ScSampleTableDisplayRow[] {
  return rows.map((row) => ({
    defect_id: String(row.defect_id ?? ""),
    rough_bin: rowValue(row, "rough_bin", 0),
    class_number: rowValue(row, "class_number", 0),
    images: rowValue(row, "images", 0),
    test_id: rowValue(row, "test_id", 0),
    wafer_x: rowValue(row, "wafer_x", 0),
    wafer_y: rowValue(row, "wafer_y", 0),
    index_x: rowValue(row, "index_x", 0),
    index_y: rowValue(row, "index_y", 0),
    adder: rowValue(row, "adder", 0),
    cluster_id: rowValue(row, "cluster_id", null),
    die_x: rowValue(row, "die_x", 0),
    die_y: rowValue(row, "die_y", 0),
    reticle_x: rowValue(row, "reticle_x", 0),
    reticle_y: rowValue(row, "reticle_y", 0),
    size_x: rowValue(row, "size_x", 0),
    size_y: rowValue(row, "size_y", 0),
    size_d: rowValue(row, "size_d", 0),
    area: rowValue(row, "area", 0),
    final_bin: rowValue(row, "final_bin", 0),
    manual_bin: rowValue(row, "manual_bin", 0),
    kill_ratio: rowValue(row, "kill_ratio", null),
    annotation_label: rowValue(row, "annotation_label", null),
    prediction_label: rowValue(row, "prediction_label", null),
    prediction_confidence: rowValue(row, "prediction_confidence", null),
  }));
}

function rowsFromArrowTable(data: unknown): ArrowJsonRow[] {
  return tableFromIPC(data as Uint8Array)
    .toArray()
    .map(arrowRowToRecord);
}

export function usePerspectiveSampleTableDataSource(
  table: Ref<Table | null>,
  scopeKey: Ref<string>,
  baseFilters?: Ref<Filter[]>,
  onRecoverableError?: (reason: string, err: unknown) => void,
  reticleExpressions?: Ref<PerspectiveExpressions>,
) {
  let activeTable: Table | null = null;
  let cachedRowsView: { table: Table; key: string; view: ManagedPerspectiveView } | null = null;
  let cachedRowsViewPromise: Promise<{
    table: Table;
    key: string;
    view: ManagedPerspectiveView;
  }> | null = null;
  let disposed = false;

  function clearCachedRowsView(): void {
    if (cachedRowsView) {
      cachedRowsView.view.retire();
      cachedRowsView = null;
    }
    cachedRowsViewPromise = null;
  }

  async function getRowsView(
    tbl: Table,
    key: string,
    filter: Array<[string, string, unknown]>,
    sort: [string, string][] | undefined,
  ): Promise<ManagedPerspectiveView> {
    if (cachedRowsView?.table === tbl && cachedRowsView.key === key) return cachedRowsView.view;
    if (cachedRowsViewPromise) {
      const pending = await cachedRowsViewPromise;
      if (!disposed && pending.table === tbl && pending.key === key && activeTable === tbl) {
        return pending.view;
      }
      if (disposed) {
        pending.view.retire();
        throw new Error("Perspective sample table data source was disposed");
      }
    }

    if (disposed) throw new Error("Perspective sample table data source was disposed");
    clearCachedRowsView();
    const managedTable = managePerspectiveTable(tbl);
    cachedRowsViewPromise = managedTable
      .view({
        expressions: reticleExpressions?.value,
        filter: filter.length ? filter : undefined,
        sort,
      } as never)
      .then((view) => ({ table: tbl, key, view }));

    const next = await cachedRowsViewPromise;
    cachedRowsViewPromise = null;
    if (disposed || activeTable !== tbl || next.table !== tbl || next.key !== key) {
      next.view.retire();
      throw new Error("Perspective sample table view was replaced before it became ready");
    }
    cachedRowsView = next;
    return next.view;
  }

  onUnmounted(() => {
    disposed = true;
    activeTable = null;
    clearCachedRowsView();
  });

  return computed<ScSampleTableDataSource | undefined>(() => {
    const tbl = table.value;
    if (!tbl) {
      clearCachedRowsView();
      activeTable = null;
      return undefined;
    }
    if (tbl !== activeTable) {
      clearCachedRowsView();
      activeTable = tbl;
    }
    const baseFilterKey = JSON.stringify(baseFilters?.value ?? []);
    return {
      scopeKey: `${scopeKey.value}:${baseFilterKey}:table`,
      async loadRows(query) {
        try {
          const filter = [...(baseFilters?.value ?? []), ...buildPerspectiveFilters(query.filter)];
          const sort = query.sort?.direction
            ? ([[perspectiveFilterField(query.sort.field), query.sort.direction]] as [
                string,
                string,
              ][])
            : undefined;
          const rowsViewKey = JSON.stringify({
            filter,
            sort,
            reticleExpressions: reticleExpressions?.value,
          });
          const rowsView = await getRowsView(tbl, rowsViewKey, filter, sort);
          const total = await rowsView.num_rows();
          const offset = Number.parseInt(query.anchor, 10) || 0;
          const endRow = Math.min(offset + query.limit, total);
          if (endRow <= offset) return { items: [], total, nextAnchor: null };
          console.time("view.to_arrow:filteredView");
          console.log("view.to_arrow:filteredView", {
            start_row: offset,
            end_row: endRow,
            total,
          });
          const rows = rowsFromArrowTable(
            await rowsView.to_arrow({ start_row: offset, end_row: endRow }),
          );
          const items = makeRows(rows);
          console.timeEnd("view.to_arrow:filteredView");
          return {
            items,
            total,
            nextAnchor: endRow < total ? String(endRow) : null,
          };
        } catch (err) {
          onRecoverableError?.("sample table rows load failed", err);
          throw err;
        }
      },
      async loadDistinctValues(query) {
        try {
          const field = perspectiveFilterField(query.field);
          const searchFilters = numericSearchFilter(field, query.search);
          if (searchFilters === null) return [];
          const filter = [
            ...(baseFilters?.value ?? []),
            ...buildPerspectiveFilters(query.filter, { omitField: query.field }),
            ...searchFilters,
          ];
          const managedTable = managePerspectiveTable(tbl);
          const managed = await managedTable.view({
            columns: [field],
            expressions: reticleExpressions?.value,
            group_by: [field],
            aggregates: { [field]: "count" },
            filter: filter.length ? filter : undefined,
          } as never);
          try {
            const total = await managed.num_rows();
            if (total === 0) return [];
            console.time("view.to_columns:distinctValues");
            const data = asRecord(
              await managed.to_columns({ start_row: 0, end_row: Math.min(total, query.limit) }),
            );
            console.timeEnd("view.to_columns:distinctValues");
            const rowPaths = data.__ROW_PATH__ as unknown[][] | undefined;
            return (rowPaths ?? [])
              .map((path) => path?.[0])
              .filter(
                (value): value is string | number =>
                  typeof value === "string" || typeof value === "number",
              );
          } finally {
            managed.retire();
          }
        } catch (err) {
          onRecoverableError?.("sample table distinct values load failed", err);
          throw err;
        }
      },
    };
  });
}
