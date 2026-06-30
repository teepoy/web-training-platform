<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { NButton, NPopover, NText } from "naive-ui";
import type { Filter, Table, ViewConfigUpdate } from "@perspective-dev/client";
import type { VxeTableDefines, VxeTablePropTypes } from "vxe-table";
import type { ScSampleTableFilter, ScSampleTableSort } from "@/features/sc/domain/sampleTable";
import type {
  ScSampleTableDisplayRow,
  ScSampleTableRowsPage,
} from "@/features/sc/domain/workbenchInteraction";
import ScRangeFilterMenu from "./ScRangeFilterMenu.vue";
import ScSetFilterMenu from "./ScSetFilterMenu.vue";
import ScTextFilterMenu from "./ScTextFilterMenu.vue";

const props = defineProps<{
  table: Table;
  viewConfig: ViewConfigUpdate;
  selectedDefectIds?: ReadonlySet<number>;
  showReclassifyColumns?: boolean;
  pageSize?: number;
  sourceVersion?: number;
}>();

const emit = defineEmits<{
  (e: "selection-change", ids: number[]): void;
}>();

interface ColumnDefinition {
  key: keyof ScSampleTableDisplayRow;
  title: string;
  width: number;
  filter: "set" | "range";
  render?: (row: ScSampleTableDisplayRow) => string;
}

interface VxeGridRef {
  clearCheckboxRow: () => Promise<unknown> | void;
  loadData: (data: VxeSampleTableRow[]) => Promise<unknown> | void;
  recalculate: (refull?: boolean) => Promise<unknown> | void;
  refreshScroll: () => Promise<unknown> | void;
  reloadData: (data: VxeSampleTableRow[]) => Promise<unknown> | void;
  setCheckboxRowKey: (key: string | number, checked: boolean) => Promise<unknown> | void;
}

type VxeSampleTableRow = ScSampleTableDisplayRow & { _isSkeleton?: boolean };

const columnDefinitions: ColumnDefinition[] = [
  {
    key: "defect_id",
    title: "Defect ID",
    width: 130,
    filter: "set",
    render: (row) => String(Number(row.defect_id)),
  },
  { key: "images", title: "Images", width: 110, filter: "range" },
  { key: "test_id", title: "Test ID", width: 120, filter: "set" },
  { key: "index_x", title: "Index X", width: 120, filter: "range" },
  { key: "index_y", title: "Index Y", width: 120, filter: "range" },
  { key: "wafer_x", title: "Wafer X", width: 120, filter: "range" },
  { key: "wafer_y", title: "Wafer Y", width: 120, filter: "range" },
  { key: "die_x", title: "Die X", width: 120, filter: "range" },
  { key: "die_y", title: "Die Y", width: 120, filter: "range" },
  { key: "size_x", title: "Size X", width: 120, filter: "range" },
  { key: "size_y", title: "Size Y", width: 120, filter: "range" },
  { key: "size_d", title: "Size D", width: 120, filter: "range" },
  { key: "area", title: "Area", width: 120, filter: "range" },
  { key: "class_number", title: "Class", width: 120, filter: "set" },
  { key: "rough_bin", title: "Rough Bin", width: 120, filter: "set" },
  { key: "final_bin", title: "Final Bin", width: 120, filter: "set" },
  { key: "manual_bin", title: "Manual Bin", width: 120, filter: "set" },
  { key: "adder", title: "Adder", width: 120, filter: "set" },
  { key: "cluster_id", title: "Cluster ID", width: 120, filter: "set" },
  {
    key: "kill_ratio",
    title: "Kill Ratio",
    width: 120,
    filter: "range",
    render: (row) => (row.kill_ratio != null ? row.kill_ratio.toFixed(3) : "-"),
  },
];

const reclassifyColumnDefinitions: ColumnDefinition[] = [
  { key: "annotation_label", title: "Annotation", width: 140, filter: "set" },
  { key: "prediction_label", title: "Prediction", width: 140, filter: "set" },
  {
    key: "prediction_confidence",
    title: "Confidence",
    width: 130,
    filter: "range",
    render: (row) =>
      row.prediction_confidence != null ? row.prediction_confidence.toFixed(3) : "-",
  },
];

const PAGE_SIZE = 1000;
const ROW_HEIGHT = 36;
const DEFAULT_TOTAL = 0;
const activeColumnDefinitions = computed(() =>
  props.showReclassifyColumns
    ? [...columnDefinitions, ...reclassifyColumnDefinitions]
    : columnDefinitions,
);
const resolvedPageSize = computed(() => props.pageSize ?? PAGE_SIZE);
const queryKey = computed(
  () => [props.table, JSON.stringify(props.viewConfig), props.sourceVersion ?? 0] as const,
);

const gridRef = ref<VxeGridRef | null>(null);
const serverTotal = ref(DEFAULT_TOTAL);
const pageError = ref<string | null>(null);
const streamStatus = ref("");
const isFetching = ref(false);
const selectedIds = ref<Set<number>>(new Set());
const tableFilter = ref<ScSampleTableFilter>({});
const tableSort = ref<ScSampleTableSort | null>(null);
const activeFilterField = ref<string | null>(null);
const filterState = ref<Record<string, { min: number | null; max: number | null }>>({});
const setFilterSearch = ref<Record<string, string>>({});
const setFilterDraft = ref<Record<string, Set<string>>>({});
const discoveredSetFilterValues = ref<Record<string, Array<string | number>>>({});
const searchedSetFilterValues = ref<Record<string, Array<string | number>>>({});
const setFilterSearchLoading = ref<Record<string, boolean>>({});
let requestVersion = 0;
let rawRows: VxeSampleTableRow[] = [];
const loadedPages = new Set<number>();
const loadingPages = new Set<number>();

const scrollYConfig = {
  enabled: true,
  gt: 0,
  oSize: 40,
};
const scrollXConfig = {
  enabled: true,
  gt: 0,
  oSize: 8,
};
const rowConfig = {
  keyField: "defect_id",
  isHover: true,
  useKey: true,
};
const cellConfig = {
  height: ROW_HEIGHT,
};
const headerCellConfig = {
  height: ROW_HEIGHT,
};
const sortConfig: VxeTablePropTypes.SortConfig<VxeSampleTableRow> = {
  remote: true,
  trigger: "cell",
  orders: ["asc", "desc", null],
};
const checkboxConfig: VxeTablePropTypes.CheckboxConfig<VxeSampleTableRow> = {
  reserve: true,
  trigger: "cell",
  checkStrictly: true,
  highlight: true,
  checkMethod: ({ row }) => !row._isSkeleton,
};

function asRecord(data: unknown): Record<string, unknown[]> {
  return data as Record<string, unknown[]>;
}

function rowAt<T>(data: Record<string, unknown[]>, key: string, index: number, fallback: T): T {
  return (data[key]?.[index] as T | undefined) ?? fallback;
}

function makeRows(data: Record<string, unknown[]>): VxeSampleTableRow[] {
  const defectIds = data.defect_id ?? [];
  const out: VxeSampleTableRow[] = [];
  for (let i = 0; i < defectIds.length; i += 1) {
    out.push({
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
  return out;
}

function makeSkeletonRow(index: number): VxeSampleTableRow {
  return {
    _isSkeleton: true,
    defect_id: `__loading_${index}`,
    rough_bin: 0,
    class_number: 0,
    images: 0,
    test_id: 0,
    wafer_x: 0,
    wafer_y: 0,
    index_x: 0,
    index_y: 0,
    adder: 0,
    cluster_id: null,
    die_x: 0,
    die_y: 0,
    reticle_x: 0,
    reticle_y: 0,
    size_x: 0,
    size_y: 0,
    size_d: 0,
    area: 0,
    final_bin: 0,
    manual_bin: 0,
    kill_ratio: null,
    annotation_label: null,
    prediction_label: null,
    prediction_confidence: null,
  };
}

function normalizeFilterValue(field: string, value: string | number): string | number {
  if (field !== "defect_id") return value;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : value;
}

function filtersFromSampleTable(filter: ScSampleTableFilter | undefined, omitField?: string) {
  const out: Array<[string, string, unknown]> = [];
  for (const [field, raw] of Object.entries(filter ?? {})) {
    if (field === omitField) continue;
    const sf = raw as {
      filterType: string;
      values?: Array<string | number>;
      type?: string;
      filter?: number;
      filterTo?: number;
    };
    if (sf.filterType === "set" && sf.values?.length) {
      out.push([field, "in", sf.values.map((value) => normalizeFilterValue(field, value))]);
    }
    if (
      sf.filterType === "number" &&
      sf.type === "inRange" &&
      typeof sf.filter === "number" &&
      typeof sf.filterTo === "number"
    ) {
      out.push([field, ">=", sf.filter], [field, "<=", sf.filterTo]);
    }
  }
  return out;
}

function getViewConfig(omitFilterField?: string): ViewConfigUpdate {
  const localFilters = filtersFromSampleTable(tableFilter.value, omitFilterField) as Filter[];
  const localSort = tableSort.value?.direction
    ? ([[tableSort.value.field, tableSort.value.direction]] as NonNullable<
        ViewConfigUpdate["sort"]
      >)
    : [];
  const config: ViewConfigUpdate = { ...props.viewConfig };
  const filter = [...(props.viewConfig.filter ?? []), ...localFilters];
  const sort = [...(props.viewConfig.sort ?? []), ...localSort];
  if (filter.length > 0) config.filter = filter;
  else delete config.filter;
  if (sort.length > 0) config.sort = sort;
  else delete config.sort;
  return config;
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

function getFilterState(field: string): {
  min: number | null;
  max: number | null;
} {
  if (!filterState.value[field]) {
    filterState.value[field] = { min: null, max: null };
  }
  return filterState.value[field];
}

function getSetFilterValues(field: string): Array<string | number> {
  const filter = tableFilter.value[field];
  return filter?.filterType === "set"
    ? filter.values.map((value) => normalizeFilterValue(field, value))
    : [];
}

function getSetFilterOptions(definition: ColumnDefinition) {
  const field = definition.key;
  const values = new Map<string, string | number>();
  for (const value of searchedSetFilterValues.value[String(field)] ?? []) {
    const normalized = normalizeFilterValue(String(field), value);
    values.set(String(normalized), normalized);
  }
  for (const value of discoveredSetFilterValues.value[String(field)] ?? []) {
    const normalized = normalizeFilterValue(String(field), value);
    values.set(String(normalized), normalized);
  }
  for (const value of getSetFilterValues(String(field))) {
    const normalized = normalizeFilterValue(String(field), value);
    values.set(String(normalized), normalized);
  }
  return Array.from(values.values())
    .sort((left, right) =>
      typeof left === "number" && typeof right === "number"
        ? left - right
        : String(left).localeCompare(String(right), undefined, {
            numeric: true,
          }),
    )
    .map((value) => ({ label: String(value), value }));
}

async function loadWindow(start: number, end: number): Promise<ScSampleTableRowsPage> {
  const view = await props.table.view(getViewConfig());
  try {
    const total = await view.num_rows();
    const safeStart = Math.max(0, Math.min(start, total));
    const safeEnd = Math.max(safeStart, Math.min(end, total));
    if (safeEnd <= safeStart) return { items: [], total, nextAnchor: null };
    const data = asRecord(await view.to_columns({ start_row: safeStart, end_row: safeEnd }));
    return {
      items: makeRows(data),
      total,
      nextAnchor: safeEnd < total ? String(safeEnd) : null,
    };
  } finally {
    await view.delete();
  }
}

async function waitForGridRef(): Promise<VxeGridRef | null> {
  if (gridRef.value) return gridRef.value;
  await nextTick();
  return gridRef.value;
}

async function syncRawRowsToTable(reset: boolean): Promise<void> {
  const table = await waitForGridRef();
  if (!table) return;
  if (reset) await table.reloadData(rawRows);
  else await table.loadData(rawRows);
}

async function loadPage(pageIndex: number): Promise<void> {
  if (pageIndex < 0 || loadedPages.has(pageIndex) || loadingPages.has(pageIndex)) return;

  const version = requestVersion;
  const start = pageIndex * resolvedPageSize.value;
  if (serverTotal.value > 0 && start >= serverTotal.value) return;
  const end = start + resolvedPageSize.value;
  loadingPages.add(pageIndex);
  pageError.value = null;
  isFetching.value = true;
  streamStatus.value = pageIndex === 0 && rawRows.length === 0 ? "Loading sample rows..." : "";
  try {
    const page = await loadWindow(start, end);
    if (version !== requestVersion) return;
    serverTotal.value = page.total;
    const isInitialLoad = rawRows.length !== page.total;
    if (isInitialLoad) {
      rawRows = Array.from({ length: page.total }, (_, index) => makeSkeletonRow(index));
    }
    for (let i = 0; i < page.items.length; i += 1) {
      Object.assign(rawRows[start + i], page.items[i], { _isSkeleton: false });
    }
    await syncRawRowsToTable(isInitialLoad);
    loadedPages.add(pageIndex);
    accumulateDiscoveredSetFilterValues(page.items);
    void nextTick(() => {
      syncCurrentPageSelection();
      void refreshGridLayout();
    });
  } catch (error) {
    if (version === requestVersion) {
      pageError.value = error instanceof Error ? error.message : "Failed to load sample table rows";
      if (pageIndex === 0) {
        rawRows = [];
        await syncRawRowsToTable(true);
        serverTotal.value = DEFAULT_TOTAL;
      }
    }
  } finally {
    loadingPages.delete(pageIndex);
    if (version === requestVersion && loadingPages.size === 0) {
      isFetching.value = false;
      streamStatus.value = "";
    }
  }
}

function accumulateDiscoveredSetFilterValues(items: ScSampleTableDisplayRow[]): void {
  for (const definition of activeColumnDefinitions.value) {
    if (definition.filter !== "set") continue;
    const field = String(definition.key);
    const values = new Map(
      (discoveredSetFilterValues.value[field] ?? []).map((value) => {
        const normalized = normalizeFilterValue(field, value);
        return [String(normalized), normalized];
      }),
    );
    for (const row of items) {
      const value = row[definition.key];
      if (typeof value === "string" || typeof value === "number") {
        const normalized = normalizeFilterValue(field, value);
        values.set(String(normalized), normalized);
      }
    }
    discoveredSetFilterValues.value[field] = Array.from(values.values());
  }
}

async function searchSetFilterOptions(field: string): Promise<void> {
  const search = setFilterSearch.value[field] ?? "";

  setFilterSearchLoading.value = { ...setFilterSearchLoading.value, [field]: true };
  try {
    const searchFilters = numericSearchFilter(field, search);
    if (searchFilters === null) {
      searchedSetFilterValues.value = { ...searchedSetFilterValues.value, [field]: [] };
      return;
    }
    const viewConfig = getViewConfig(field);
    const view = await props.table.view({
      ...viewConfig,
      columns: [field],
      group_by: [field],
      aggregates: { [field]: "count" },
      filter: [...(viewConfig.filter ?? []), ...(searchFilters as Filter[])],
    });
    try {
      const total = await view.num_rows();
      const data = asRecord(await view.to_columns({ start_row: 0, end_row: Math.min(total, 200) }));
      const rowPaths = data.__ROW_PATH__ as unknown[][] | undefined;
      searchedSetFilterValues.value = {
        ...searchedSetFilterValues.value,
        [field]: (rowPaths ?? [])
          .map((path) => path?.[0])
          .filter(
            (value): value is string | number =>
              typeof value === "string" || typeof value === "number",
          ),
      };
    } finally {
      await view.delete();
    }
  } finally {
    setFilterSearchLoading.value = { ...setFilterSearchLoading.value, [field]: false };
  }
}

function resetRows(): void {
  requestVersion += 1;
  loadedPages.clear();
  loadingPages.clear();
  rawRows = [];
  void syncRawRowsToTable(true);
  serverTotal.value = DEFAULT_TOTAL;
  void loadPage(0);
}

function applySetFilter(field: string, values: Array<string | number>): void {
  const next = { ...tableFilter.value };
  if (values.length === 0) {
    delete next[field];
  } else {
    next[field] = {
      filterType: "set",
      values: values.map((value) => normalizeFilterValue(field, value)),
    };
  }
  tableFilter.value = next;
  resetRows();
}

function applyRangeFilter(field: string): void {
  const state = filterState.value[field];
  if (!state || state.min === null || state.max === null || state.min > state.max) {
    return;
  }
  tableFilter.value = {
    ...tableFilter.value,
    [field]: {
      filterType: "number",
      type: "inRange",
      filter: state.min,
      filterTo: state.max,
    },
  };
  resetRows();
}

function clearFilter(field: string): void {
  const next = { ...tableFilter.value };
  delete next[field];
  filterState.value[field] = { min: null, max: null };
  tableFilter.value = next;
  resetRows();
}

function clearAllFilters(): void {
  setFilterSearch.value = {};
  setFilterDraft.value = {};
  filterState.value = {};
  tableFilter.value = {};
  resetRows();
}

function openFilter(definition: ColumnDefinition, open: boolean): void {
  const field = String(definition.key);
  activeFilterField.value = open ? field : null;
  if (!open || definition.filter !== "set") return;
  setFilterDraft.value[field] = new Set(getSetFilterValues(field).map(String));
}

function isColumnFiltered(field: string): boolean {
  return Boolean(tableFilter.value[field]);
}

function handleSortChange(event: VxeTableDefines.SortChangeEventParams<VxeSampleTableRow>): void {
  const field = event.field ?? event.property ?? tableSort.value?.field ?? "";
  tableSort.value =
    event.order === "asc" || event.order === "desc" ? { field, direction: event.order } : null;
  resetRows();
}

function rowDefectId(row: VxeSampleTableRow): number | null {
  if (row._isSkeleton) return null;
  const id = Number(row.defect_id);
  return Number.isFinite(id) ? id : null;
}

function emitSelection(): void {
  emit("selection-change", Array.from(selectedIds.value));
}

function handleCheckboxChange(
  event: VxeTableDefines.CheckboxChangeEventParams<VxeSampleTableRow>,
): void {
  if (!event.row) return;
  const id = rowDefectId(event.row);
  if (id === null) return;
  const next = new Set(selectedIds.value);
  if (event.checked) next.add(id);
  else next.delete(id);
  selectedIds.value = next;
  emitSelection();
}

function handleCheckboxAll(event: VxeTableDefines.CheckboxAllEventParams<VxeSampleTableRow>): void {
  const next = new Set(selectedIds.value);
  for (const row of rawRows) {
    const id = rowDefectId(row);
    if (id === null) continue;
    if (event.checked) next.add(id);
    else next.delete(id);
  }
  selectedIds.value = next;
  emitSelection();
}

function handleCellClick(event: VxeTableDefines.CellClickEventParams<VxeSampleTableRow>): void {
  if (!event.row || event.column?.type === "checkbox") return;
  const id = rowDefectId(event.row);
  if (id === null) return;
  const next = new Set(selectedIds.value);
  const checked = !next.has(id);
  if (checked) next.add(id);
  else next.delete(id);
  selectedIds.value = next;
  void gridRef.value?.setCheckboxRowKey(id, checked);
  emitSelection();
}

function syncCurrentPageSelection(): void {
  for (const row of rawRows) {
    const id = rowDefectId(row);
    if (id !== null) {
      void gridRef.value?.setCheckboxRowKey(id, selectedIds.value.has(id));
    }
  }
}

function clearSelection(): void {
  selectedIds.value = new Set();
  void gridRef.value?.clearCheckboxRow();
  emitSelection();
}

function renderCell(definition: ColumnDefinition, row: VxeSampleTableRow): string {
  if (row._isSkeleton) return "";
  if (definition.render) return definition.render(row);
  const value = row[definition.key];
  return value == null || value === "" ? "-" : String(value);
}

function sortOrder(field: string): VxeTablePropTypes.SortOrder {
  return tableSort.value?.field === field ? tableSort.value.direction : null;
}

async function refreshGridLayout(): Promise<void> {
  await nextTick();
  await gridRef.value?.recalculate(true);
  await gridRef.value?.refreshScroll();
}

function handleScroll(event: VxeTableDefines.ScrollEventParams<VxeSampleTableRow>): void {
  if (event.type !== "body" || serverTotal.value <= 0) return;
  const startRowIndex = Math.floor(event.scrollTop / ROW_HEIGHT);
  const visibleRowsCount = Math.ceil(event.bodyHeight / ROW_HEIGHT);
  const endRowIndex = startRowIndex + Math.max(visibleRowsCount, 1);
  const startPage = Math.floor(startRowIndex / resolvedPageSize.value);
  const endPage = Math.floor(endRowIndex / resolvedPageSize.value);
  const maxPage = Math.ceil(serverTotal.value / resolvedPageSize.value) - 1;
  for (let page = startPage; page <= endPage; page += 1) {
    if (page <= maxPage) void loadPage(page);
  }
  if (endPage + 1 <= maxPage) void loadPage(endPage + 1);
  if (startPage - 1 >= 0) void loadPage(startPage - 1);
}

watch(queryKey, resetRows, { immediate: true });

watch(
  () => props.selectedDefectIds,
  (ids) => {
    selectedIds.value = new Set(ids ?? []);
    void nextTick(syncCurrentPageSelection);
  },
  { immediate: true },
);

watch(
  tableFilter,
  (filter) => {
    for (const definition of activeColumnDefinitions.value) {
      const field = String(definition.key);
      const value = filter[field];
      filterState.value[field] =
        value?.filterType === "number" && value.type === "inRange"
          ? { min: value.filter, max: value.filterTo }
          : { min: null, max: null };
    }
  },
  { immediate: true, deep: true },
);

onMounted(() => {
  if (rawRows.length > 0) {
    void gridRef.value?.reloadData(rawRows);
  }
  void refreshGridLayout();
});

watch(
  () => serverTotal.value,
  () => {
    void refreshGridLayout();
  },
);

defineExpose({
  getDefectCoords(defectId: number):
    | {
        waferX: number;
        waferY: number;
        dieX: number;
        dieY: number;
        reticleX: number;
        reticleY: number;
      }
    | undefined {
    const row = rawRows.find((r) => Number(r.defect_id) === defectId);
    if (!row || row._isSkeleton) return undefined;
    return {
      waferX: row.wafer_x,
      waferY: row.wafer_y,
      dieX: row.die_x,
      dieY: row.die_y,
      reticleX: row.reticle_x,
      reticleY: row.reticle_y,
    };
  },
});
</script>

<template>
  <div class="sst-vxe">
    <div class="sst-vxe-header">
      <NText depth="2" class="sst-vxe-header-label"> Sample Data ({{ serverTotal }}) </NText>
      <div class="sst-vxe-header-actions">
        <NButton v-if="selectedIds.size > 0" size="tiny" quaternary @click="clearSelection">
          Clear Selection ({{ selectedIds.size }})
        </NButton>
        <NButton
          v-if="Object.keys(tableFilter).length > 0"
          size="tiny"
          quaternary
          @click="clearAllFilters"
        >
          Clear All Filters
        </NButton>
        <NText v-if="streamStatus" depth="3" class="sst-vxe-status-info">
          {{ streamStatus }}
        </NText>
      </div>
    </div>
    <vxe-table
      ref="gridRef"
      class="sst-vxe-grid"
      border
      auto-resize
      show-overflow
      size="mini"
      height="100%"
      :loading="isFetching && serverTotal === 0"
      :row-config="rowConfig"
      :cell-config="cellConfig"
      :header-cell-config="headerCellConfig"
      :checkbox-config="checkboxConfig"
      :sort-config="sortConfig"
      :scroll-y="scrollYConfig"
      :scroll-x="scrollXConfig"
      @sort-change="handleSortChange"
      @checkbox-change="handleCheckboxChange"
      @checkbox-all="handleCheckboxAll"
      @cell-click="handleCellClick"
      @scroll="handleScroll"
    >
      <vxe-column type="checkbox" width="44" fixed="left" align="center" />
      <vxe-column
        v-for="definition in activeColumnDefinitions"
        :key="String(definition.key)"
        :field="String(definition.key)"
        :title="definition.title"
        :width="definition.width"
        :fixed="definition.key === 'defect_id' ? 'left' : undefined"
        sortable
        :order="sortOrder(String(definition.key))"
      >
        <template #header>
          <div class="sst-vxe-column-header">
            <span class="sst-vxe-column-title">{{ definition.title }}</span>
            <NPopover
              trigger="click"
              placement="bottom-start"
              :show="activeFilterField === String(definition.key)"
              @update:show="openFilter(definition, $event)"
            >
              <template #trigger>
                <NButton
                  size="tiny"
                  quaternary
                  class="sst-vxe-filter-button"
                  :class="{
                    'sst-vxe-filter-button--active': isColumnFiltered(String(definition.key)),
                  }"
                  @click.stop
                >
                  Filter
                </NButton>
              </template>
              <ScTextFilterMenu
                v-if="definition.key === 'defect_id'"
                :applied-values="getSetFilterValues('defect_id')"
                @apply="applySetFilter('defect_id', $event)"
                @close="activeFilterField = null"
              />
              <ScSetFilterMenu
                v-else-if="definition.filter === 'set'"
                :search="setFilterSearch[String(definition.key)] ?? ''"
                :applied-values="getSetFilterValues(String(definition.key))"
                :draft-values="Array.from(setFilterDraft[String(definition.key)] ?? [])"
                :options="getSetFilterOptions(definition)"
                @update:search="setFilterSearch[String(definition.key)] = $event"
                @update:draft-values="setFilterDraft[String(definition.key)] = new Set($event)"
                @search-options="searchSetFilterOptions(String(definition.key))"
                @apply="applySetFilter(String(definition.key), $event)"
                @close="activeFilterField = null"
              />
              <ScRangeFilterMenu
                v-else
                :min="getFilterState(String(definition.key)).min"
                :max="getFilterState(String(definition.key)).max"
                @update:min="getFilterState(String(definition.key)).min = $event"
                @update:max="getFilterState(String(definition.key)).max = $event"
                @apply="applyRangeFilter(String(definition.key))"
                @clear="clearFilter(String(definition.key))"
                @close="activeFilterField = null"
              />
            </NPopover>
          </div>
        </template>
        <template #default="{ row }">
          {{ renderCell(definition, row as VxeSampleTableRow) }}
        </template>
      </vxe-column>
      <template #empty>
        <div class="sst-vxe-empty">
          <NText depth="3">
            {{ isFetching ? "Loading sample rows..." : pageError ? pageError : "No sample rows" }}
          </NText>
        </div>
      </template>
    </vxe-table>

    <NText v-if="pageError" type="error" class="sst-vxe-error">
      {{ pageError }}
    </NText>
  </div>
</template>

<style scoped>
.sst-vxe {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--cv-card-bg, #1a1a2e);
  border: 1px solid var(--cv-border, rgba(255, 255, 255, 0.1));
  border-radius: 8px;
  padding: 8px 10px;
}

.sst-vxe-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  flex-shrink: 0;
}

.sst-vxe-header-label {
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.sst-vxe-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sst-vxe-status-info {
  font-size: 11px;
}

.sst-vxe-grid {
  flex: 1;
  min-height: 0;
  width: 100%;
}

.sst-vxe-column-header {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

.sst-vxe-column-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sst-vxe-filter-button {
  flex: 0 0 auto;
  padding: 0 4px;
  font-size: 10px;
}

.sst-vxe-filter-button--active {
  color: #63e6be;
}

.sst-vxe-error {
  padding-top: 4px;
  font-size: 12px;
}

:deep(.vxe-cell) {
  line-height: 30px;
}
</style>
