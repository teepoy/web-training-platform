<!--
  DataTableWidget — sortable table rendered from inline column/row data.

  Inline data shape: { inline: { columns: string[], rows: any[][] } }

  Config props:
    maxRows — cap visible rows (default 100)
    striped — alternate row shading (default true)
-->
<script setup lang="ts">
import { computed, inject, ref } from "vue";
import {
  SIDEBAR_WIDGET_INTERACTION_KEY,
  type SidebarWidgetIntent,
  type SidebarWidgetInteractionConfig,
} from "@platform/widget-sdk";

const props = defineProps<{
  data?: Record<string, unknown> | null;
  config?: Record<string, unknown>;
  size?: "compact" | "normal" | "large";
}>();

const interaction = inject(SIDEBAR_WIDGET_INTERACTION_KEY, null);

const maxRows = computed(() => Number(props.config?.maxRows ?? 100));

const interactionConfig = computed<SidebarWidgetInteractionConfig | null>(() => {
  const raw = props.config?.interaction;
  if (!raw || typeof raw !== "object") {
    return null;
  }
  return raw as SidebarWidgetInteractionConfig;
});

interface TableColumn {
  key: string;
  label: string;
}

interface InteractiveRow {
  id: string;
  cells: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

interface LegacyTableData {
  mode: "legacy";
  columns: string[];
  rows: unknown[][];
}

interface InteractiveTableData {
  mode: "interactive";
  columns: TableColumn[];
  rows: InteractiveRow[];
}

type TableData = LegacyTableData | InteractiveTableData;

const tableData = computed<TableData | null>(() => {
  if (!props.data) return null;
  const raw = (props.data as Record<string, unknown>).inline ?? props.data;
  if (!raw || typeof raw !== "object") return null;
  const d = raw as Record<string, unknown>;
  const columns = d.columns;
  const rows = d.rows;
  if (!Array.isArray(columns) || !Array.isArray(rows)) return null;

  const interactiveColumns = columns.every((col) => {
    if (!col || typeof col !== "object") {
      return false;
    }
    const c = col as Record<string, unknown>;
    return typeof c.key === "string";
  });

  const interactiveRows = rows.every((row) => {
    if (!row || typeof row !== "object") {
      return false;
    }
    const r = row as Record<string, unknown>;
    return typeof r.id === "string" && !!r.cells && typeof r.cells === "object";
  });

  if (interactiveColumns && interactiveRows) {
    const parsedColumns = (columns as Array<Record<string, unknown>>).map((col) => ({
      key: col.key as string,
      label: typeof col.label === "string" ? (col.label as string) : (col.key as string),
    }));

    return {
      mode: "interactive",
      columns: parsedColumns,
      rows: (rows as Array<Record<string, unknown>>)
        .slice(0, maxRows.value)
        .map((row) => ({
          id: row.id as string,
          cells: row.cells as Record<string, unknown>,
          metadata: row.metadata as Record<string, unknown> | undefined,
        })),
    };
  }

  return {
    mode: "legacy",
    columns: (columns as unknown[]).map((col) => String(col)),
    rows: (rows as unknown[][]).slice(0, maxRows.value),
  };
});

const sortCol = ref<number | null>(null);
const sortAsc = ref(true);

function toggleSort(colIdx: number) {
  if (sortCol.value === colIdx) {
    sortAsc.value = !sortAsc.value;
  } else {
    sortCol.value = colIdx;
    sortAsc.value = true;
  }
}

const selectedIds = computed(() => {
  const cfg = interactionConfig.value;
  if (!cfg?.collection) {
    return new Set<string>();
  }
  const ids = interaction?.value.state.collections?.[cfg.collection]?.selection.ids ?? [];
  return new Set(ids);
});

const selectedRowCount = computed(() => selectedIds.value.size);

const sortedRows = computed<unknown[] | null>(() => {
  const data = tableData.value;
  if (!data) return null;
  const rows = [...data.rows];
  if (sortCol.value === null) return rows;
  const ci = sortCol.value;
  const dir = sortAsc.value ? 1 : -1;

  const valueForSort =
    data.mode === "interactive"
      ? (row: unknown): unknown => {
          const columnKey = data.columns[ci]?.key;
          if (!columnKey) return null;
          return (row as InteractiveRow).cells[columnKey];
        }
      : (row: unknown): unknown => (row as unknown[])[ci];

  rows.sort((a, b) => {
    const va = valueForSort(a);
    const vb = valueForSort(b);
    if (va === vb) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
    return String(va).localeCompare(String(vb)) * dir;
  });
  return rows;
});

const visibleRows = computed<unknown[] | null>(() => {
  const rows = sortedRows.value;
  if (!rows) {
    return null;
  }

  const cfg = interactionConfig.value;
  const data = tableData.value;
  if (!cfg?.filterFromSelection || !cfg.collection || data?.mode !== "interactive") {
    return rows;
  }

  const filterState = interaction?.value.state.collections?.[cfg.collection]?.filter;
  if (!filterState || filterState.mode === "all") {
    return rows;
  }

  const idSet = new Set(filterState.ids);
  return (rows as InteractiveRow[]).filter((row) => idSet.has(row.id));
});

function valueForDisplay(row: unknown, colIdx: number): unknown {
  const data = tableData.value;
  if (!data) {
    return "";
  }
  if (data.mode === "interactive") {
    const col = data.columns[colIdx];
    if (!col) {
      return "";
    }
    return (row as InteractiveRow).cells[col.key];
  }
  return (row as unknown[])[colIdx];
}

function emitIntent(intent: SidebarWidgetIntent): void {
  interaction?.value.dispatch(intent);
}

function selectionIntentType(entity: SidebarWidgetInteractionConfig["entity"]): SidebarWidgetIntent["type"] {
  if (entity === "prediction") {
    return "select-predictions";
  }
  return "select-samples";
}

function onRowClick(row: unknown, event: MouseEvent): void {
  const data = tableData.value;
  const cfg = interactionConfig.value;
  if (!data || data.mode !== "interactive" || !cfg?.collection || !cfg.emitSelection) {
    return;
  }

  const rowId = (row as InteractiveRow).id;
  const operation: SidebarWidgetIntent["operation"] =
    event.metaKey || event.ctrlKey ? "toggle" : "replace";

  emitIntent({
    type: selectionIntentType(cfg.entity),
    operation,
    values: [rowId],
    sourcePanelId: "data-table",
    metadata: {
      collection: cfg.collection,
      entity: cfg.entity,
      target: "selection",
    },
  });

  if (cfg.filterFromSelection && operation === "replace") {
    emitIntent({
      type: "apply-filter",
      operation: "replace",
      values: [rowId],
      sourcePanelId: "data-table",
      metadata: {
        collection: cfg.collection,
        entity: cfg.entity,
        target: "filter",
        filterMode: "selected-only",
      },
    });
  }
}

function rowClass(row: unknown, rowIndex: number): Record<string, boolean> {
  const classes: Record<string, boolean> = {
    "dtw-row--alt": rowIndex % 2 === 1,
  };

  const data = tableData.value;
  const cfg = interactionConfig.value;
  if (data?.mode === "interactive" && cfg?.followSelection) {
    classes["dtw-row--selected"] = selectedIds.value.has((row as InteractiveRow).id);
  }

  return classes;
}

function clearLinkedState(): void {
  const cfg = interactionConfig.value;
  if (!cfg?.collection) {
    return;
  }
  emitIntent({
    type: "clear-selection",
    operation: "clear",
    values: [],
    sourcePanelId: "data-table",
    metadata: {
      collection: cfg.collection,
      entity: cfg.entity,
      target: "both",
    },
  });
}

const containerHeight = computed(() => {
  switch (props.size) {
    case "compact":
      return "140px";
    case "large":
      return "300px";
    default:
      return "200px";
  }
});
</script>

<template>
  <div class="dtw">
    <div v-if="!tableData" class="dtw-empty">No table data</div>
    <div v-else class="dtw-scroll" :style="{ maxHeight: containerHeight }">
      <table class="dtw-table">
        <thead>
          <tr>
            <th
              v-for="(col, i) in tableData.columns"
              :key="i"
              @click="toggleSort(i)"
              class="dtw-th"
            >
              {{ typeof col === "string" ? col : col.label }}
              <span v-if="sortCol === i" class="dtw-sort">{{ sortAsc ? "▲" : "▼" }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, ri) in visibleRows"
            :key="ri"
            :class="rowClass(row, ri)"
            @click="onRowClick(row, $event)"
          >
            <td v-for="(_, ci) in tableData.columns" :key="ci" class="dtw-td">
              {{ valueForDisplay(row, ci) ?? "" }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="tableData" class="dtw-footer">
      <span>{{ (visibleRows?.length ?? 0) }} row{{ (visibleRows?.length ?? 0) === 1 ? "" : "s" }}</span>
      <button v-if="selectedRowCount > 0" class="dtw-clear" @click="clearLinkedState">Clear</button>
    </div>
  </div>
</template>

<style scoped>
.dtw {
  width: 100%;
}
.dtw-empty {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.4);
  padding: 12px 0;
  text-align: center;
}
.dtw-scroll {
  overflow: auto;
}
.dtw-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}
.dtw-th {
  position: sticky;
  top: 0;
  background: rgba(30, 30, 46, 0.95);
  color: rgba(255, 255, 255, 0.7);
  font-weight: 600;
  padding: 4px 6px;
  text-align: left;
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
}
.dtw-th:hover {
  color: #fff;
}
.dtw-sort {
  margin-left: 2px;
  font-size: 9px;
}
.dtw-td {
  padding: 3px 6px;
  color: rgba(255, 255, 255, 0.75);
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 150px;
}
.dtw-row--alt {
  background: rgba(255, 255, 255, 0.02);
}
.dtw-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.35);
  padding: 4px 0 0;
}

.dtw-row--selected {
  background: rgba(147, 204, 255, 0.22);
}

.dtw-clear {
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 4px;
  color: rgba(255, 255, 255, 0.85);
  font-size: 10px;
  padding: 2px 8px;
  cursor: pointer;
}

.dtw-clear:hover {
  background: rgba(255, 255, 255, 0.15);
}
</style>
