<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { CSSProperties } from "vue";
import { NButton, NIcon, NPopover, NText } from "naive-ui";
import type { VxeTableDefines, VxeTablePropTypes } from "vxe-table";
import {
  ArrowDownOutline,
  ArrowUpOutline,
  FunnelOutline,
  SwapVerticalOutline,
} from "@vicons/ionicons5";
import type { ScSampleTableFilter, ScSampleTableSort } from "@/features/sc/domain/sampleTable";
import type { ScTableSelectionConstraint } from "@/features/sc/domain/workbenchDataSource";
import type { ScSampleTableDisplayRow } from "@/features/sc/domain/workbenchInteraction";
import type { ScSampleTableDataSource } from "@/features/sc/domain/workbenchInteraction";
import { ArrowBackedRows } from "./arrowBackedRows";
import {
  scSampleTableColumns,
  type ScSampleTableColumnDefinition as ColumnDefinition,
} from "./scSampleTableColumns";
import ScRangeFilterMenu from "./ScRangeFilterMenu.vue";
import ScSetFilterMenu from "./ScSetFilterMenu.vue";
import ScTextFilterMenu from "./ScTextFilterMenu.vue";
import type { ScSampleTableBaseProps, ScSampleTableEmits } from "./scSampleTableContract";

interface ScSampleTableVxeProps extends ScSampleTableBaseProps {
  dataSource: ScSampleTableDataSource;
  defectIds?: string[];
  pageSize?: number;
}

const props = defineProps<ScSampleTableVxeProps>();

const emit = defineEmits<ScSampleTableEmits>();

interface VxeRowsPage {
  items: ScSampleTableDisplayRow[];
  total: number;
  nextAnchor: string | null;
}

interface VxeGridRef {
  clearCheckboxRow: () => Promise<unknown> | void;
  getScrollData: () => {
    clientWidth: number;
    scrollLeft: number;
    scrollWidth: number;
  };
  loadData: (data: VxeSampleTableRow[]) => Promise<unknown> | void;
  recalculate: (refull?: boolean) => Promise<unknown> | void;
  refreshScroll: () => Promise<unknown> | void;
  reloadData: (data: VxeSampleTableRow[]) => Promise<unknown> | void;
  scrollTo: (scrollLeft: number | null, scrollTop: number | null) => Promise<unknown> | void;
  setCheckboxRowKey: (key: string | number, checked: boolean) => Promise<unknown> | void;
}

type VxeSampleTableRow = Partial<ScSampleTableDisplayRow> & {
  defect_id: string;
  _isHydrated?: boolean;
};

const PAGE_SIZE = 250;
const ROW_HEIGHT = 36;
const SCROLLBAR_SIZE = 10;
const MIN_SCROLL_THUMB_SIZE = 24;
const DEFAULT_TOTAL = 0;
const DEFAULT_TABLE_SORT: ScSampleTableSort = {
  field: "defect_id",
  direction: "asc",
};
const activeColumnDefinitions = computed(() =>
  scSampleTableColumns(props.showReclassifyColumns === true),
);
const resolvedPageSize = computed(() => props.pageSize ?? PAGE_SIZE);

let arrowRows = new ArrowBackedRows();
let rawRows = arrowRows.rows as VxeSampleTableRow[];
let displayRows: VxeSampleTableRow[] = [];
const gridRef = ref<VxeGridRef | null>(null);
const gridHostRef = ref<HTMLElement | null>(null);
const virtualRailRef = ref<HTMLElement | null>(null);
const xScrollbarRailRef = ref<HTMLElement | null>(null);
const yScrollbarRailRef = ref<HTMLElement | null>(null);
const serverTotal = ref(DEFAULT_TOTAL);
const storageStats = ref(arrowRows.getStats());
const pageError = ref<string | null>(null);
const streamStatus = ref("");
const isFetching = ref(false);
// In explicit mode this set contains selected IDs. In all-results mode it
// contains only the exceptions, so a 300k-row selection stays constant-size.
const selectionDeltaIds = ref<Set<number>>(new Set());
const allMatchingRowsSelected = ref(false);
const tableFilter = ref<ScSampleTableFilter>({ ...(props.filter ?? {}) });
const tableSort = ref<ScSampleTableSort>(normalizeTableSort(props.sort));
const filterPopoverVersion = ref(0);
const filterState = ref<Record<string, { min: number | null; max: number | null }>>({});
const setFilterSearch = ref<Record<string, string>>({});
const setFilterDraft = ref<Record<string, Set<string>>>({});
const discoveredSetFilterValues = ref<Record<string, Array<string | number>>>({});
const searchedSetFilterValues = ref<Record<string, Array<string | number>>>({});
const setFilterSearchLoading = ref<Record<string, boolean>>({});
let requestVersion = 0;
const loadedDefectIds = new Set<number>();
let loadingRequest: { page: number; version: number } | null = null;
let pendingHorizontalScrollRestore: { version: number; scrollLeft: number } | null = null;
let pendingRowsReplacementVersion: number | null = null;
let requestedPage = 0;
let renderedPage = -1;
let resizeObserver: ResizeObserver | null = null;
let scrollbarDragState: {
  axis: "x" | "y";
  startPointer: number;
  startScroll: number;
  scrollableDistance: number;
  trackDistance: number;
} | null = null;

interface ScrollbarMetrics {
  xClientSize: number;
  xScrollSize: number;
  xPosition: number;
  xTrackSize: number;
  yClientSize: number;
  yScrollSize: number;
  yPosition: number;
  yTrackSize: number;
}

const scrollbarMetrics = ref<ScrollbarMetrics>({
  xClientSize: 0,
  xScrollSize: 0,
  xPosition: 0,
  xTrackSize: 0,
  yClientSize: 0,
  yScrollSize: 0,
  yPosition: 0,
  yTrackSize: 0,
});

function thumbSize(clientSize: number, scrollSize: number, trackSize: number): number {
  if (trackSize <= 0) return 0;
  if (clientSize <= 0 || scrollSize <= clientSize) return trackSize;
  return Math.min(
    trackSize,
    Math.max(MIN_SCROLL_THUMB_SIZE, (clientSize / scrollSize) * trackSize),
  );
}

function thumbOffset(
  position: number,
  clientSize: number,
  scrollSize: number,
  trackSize: number,
  size: number,
): number {
  const scrollableDistance = scrollSize - clientSize;
  const trackDistance = trackSize - size;
  if (scrollableDistance <= 0 || trackDistance <= 0) return 0;
  return (position / scrollableDistance) * trackDistance;
}

const xThumbSize = computed(() =>
  thumbSize(
    scrollbarMetrics.value.xClientSize,
    scrollbarMetrics.value.xScrollSize,
    scrollbarMetrics.value.xTrackSize,
  ),
);
const yThumbSize = computed(() =>
  thumbSize(
    scrollbarMetrics.value.yClientSize,
    scrollbarMetrics.value.yScrollSize,
    scrollbarMetrics.value.yTrackSize,
  ),
);
const xThumbStyle = computed<CSSProperties>(() => ({
  width: `${xThumbSize.value}px`,
  transform: `translateX(${thumbOffset(
    scrollbarMetrics.value.xPosition,
    scrollbarMetrics.value.xClientSize,
    scrollbarMetrics.value.xScrollSize,
    scrollbarMetrics.value.xTrackSize,
    xThumbSize.value,
  )}px)`,
}));
const yThumbStyle = computed<CSSProperties>(() => ({
  height: `${yThumbSize.value}px`,
  transform: `translateY(${thumbOffset(
    scrollbarMetrics.value.yPosition,
    scrollbarMetrics.value.yClientSize,
    scrollbarMetrics.value.yScrollSize,
    scrollbarMetrics.value.yTrackSize,
    yThumbSize.value,
  )}px)`,
}));

const virtualYConfig: VxeTablePropTypes.VirtualYConfig = {
  enabled: true,
  gt: 0,
  mode: "scroll",
  oSize: 40,
};
const virtualXConfig: VxeTablePropTypes.VirtualXConfig = {
  enabled: true,
  gt: 0,
  oSize: 8,
  scrollToLeftOnChange: false,
};
const scrollbarConfig: VxeTablePropTypes.ScrollbarConfig = {
  height: SCROLLBAR_SIZE,
  width: SCROLLBAR_SIZE,
  x: {
    visible: "visible",
  },
  y: {
    visible: "hidden",
  },
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
const checkboxConfig: VxeTablePropTypes.CheckboxConfig<VxeSampleTableRow> = {
  reserve: true,
  trigger: "cell",
  checkStrictly: true,
  showHeader: true,
  highlight: true,
  checkMethod: ({ row }) => rowDefectId(row) !== null,
};

function normalizeFilterValue(field: string, value: string | number): string | number {
  if (field !== "defect_id") return value;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : value;
}

function normalizeTableSort(sort: ScSampleTableSort | null | undefined): ScSampleTableSort {
  return sort ?? DEFAULT_TABLE_SORT;
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

async function loadWindow(start: number, end: number): Promise<VxeRowsPage> {
  const page = await props.dataSource.loadRows({
    defectIds: props.defectIds ?? [],
    anchor: String(start),
    limit: Math.max(0, end - start),
    filter: tableFilter.value,
    sort: tableSort.value,
  });
  return page;
}

async function waitForGridRef(): Promise<VxeGridRef | null> {
  if (gridRef.value) return gridRef.value;
  await nextTick();
  return gridRef.value;
}

async function syncRawRowsToTable(): Promise<void> {
  const table = await waitForGridRef();
  if (!table) return;
  const scrollLeft = table.getScrollData().scrollLeft;
  await table.reloadData(displayRows);
  await table.scrollTo(scrollLeft, null);
  storageStats.value = arrowRows.getStats();
}

async function loadPage(pageIndex: number): Promise<void> {
  if (
    pageIndex < 0 ||
    renderedPage === pageIndex ||
    (loadingRequest?.page === pageIndex && loadingRequest.version === requestVersion)
  ) {
    return;
  }

  const version = requestVersion;
  const request = { page: pageIndex, version };
  const start = pageIndex * resolvedPageSize.value;
  if (serverTotal.value > 0 && start >= serverTotal.value) return;
  const end = start + resolvedPageSize.value;
  loadingRequest = request;
  pageError.value = null;
  isFetching.value = true;
  const replacesRows = pendingRowsReplacementVersion === version;
  const nextArrowRows = replacesRows ? new ArrowBackedRows() : arrowRows;
  streamStatus.value =
    pageIndex === 0 && (replacesRows || rawRows.length === 0) ? "Loading sample rows..." : "";
  try {
    const page = await loadWindow(start, end);
    if (version !== requestVersion || pageIndex !== requestedPage) return;
    nextArrowRows.resetWithoutDefectIds(page.total);
    const items = page.items.map((item) => ({ ...item, _isHydrated: true }));
    if (version !== requestVersion || pageIndex !== requestedPage) return;
    if (replacesRows) {
      arrowRows = nextArrowRows;
      rawRows = arrowRows.rows as VxeSampleTableRow[];
      pendingRowsReplacementVersion = null;
    }
    serverTotal.value = page.total;
    displayRows = items;
    loadedDefectIds.clear();
    for (const row of items) {
      const id = rowDefectId(row);
      if (id !== null) loadedDefectIds.add(id);
    }
    await syncRawRowsToTable();
    renderedPage = pageIndex;
    accumulateDiscoveredSetFilterValues(items);
    const horizontalScrollRestore = pendingHorizontalScrollRestore?.scrollLeft;
    if (horizontalScrollRestore !== undefined) {
      pendingHorizontalScrollRestore = null;
    }
    void nextTick(() => {
      syncCurrentPageSelection();
      void refreshGridLayout(horizontalScrollRestore);
    });
  } catch (error) {
    if (version === requestVersion) {
      pageError.value = error instanceof Error ? error.message : "Failed to load sample table rows";
    }
  } finally {
    if (loadingRequest === request) {
      loadingRequest = null;
    }
    if (version === requestVersion && loadingRequest === null) {
      isFetching.value = false;
      streamStatus.value = "";
    }
  }
}

function accumulateDiscoveredSetFilterValues(items: VxeSampleTableRow[]): void {
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
    searchedSetFilterValues.value = {
      ...searchedSetFilterValues.value,
      [field]:
        (await props.dataSource.loadDistinctValues?.({
          field,
          search,
          limit: 200,
          filter: tableFilter.value,
          sort: tableSort.value,
        })) ?? [],
    };
  } finally {
    setFilterSearchLoading.value = { ...setFilterSearchLoading.value, [field]: false };
  }
}

async function resetRows(): Promise<void> {
  const scrollLeft = gridRef.value?.getScrollData().scrollLeft ?? 0;
  const version = ++requestVersion;
  pendingHorizontalScrollRestore = { version, scrollLeft };
  pendingRowsReplacementVersion = version;
  loadingRequest = null;
  loadedDefectIds.clear();
  resetVirtualPosition();
  pageError.value = null;
  isFetching.value = true;
  streamStatus.value = "Loading sample rows...";

  if (version !== requestVersion) return;
  await loadPage(0);
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
  emit("filter-change", next);
  filterPopoverVersion.value += 1;
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
  emit("filter-change", tableFilter.value);
  filterPopoverVersion.value += 1;
}

function clearFilter(field: string): void {
  const next = { ...tableFilter.value };
  delete next[field];
  filterState.value[field] = { min: null, max: null };
  tableFilter.value = next;
  emit("filter-change", next);
  filterPopoverVersion.value += 1;
}

function clearAllFilters(): void {
  setFilterSearch.value = {};
  setFilterDraft.value = {};
  filterState.value = {};
  tableFilter.value = {};
  emit("filter-change", {});
  filterPopoverVersion.value += 1;
}

function openFilter(definition: ColumnDefinition, open: boolean): void {
  const field = String(definition.key);
  if (!open || definition.filter !== "set") return;
  setFilterDraft.value[field] = new Set(getSetFilterValues(field).map(String));
}

function closeFilterPopover(): void {
  filterPopoverVersion.value += 1;
}

function isColumnFiltered(field: string): boolean {
  return Boolean(tableFilter.value[field]);
}

function cycleSort(field: string): void {
  const currentOrder = sortOrder(field);
  const nextOrder = currentOrder === null ? "asc" : currentOrder === "asc" ? "desc" : null;
  tableSort.value = nextOrder ? { field, direction: nextOrder } : DEFAULT_TABLE_SORT;
  emit("sort-change", {
    field,
    direction: nextOrder,
  });
}

function sortIcon(field: string) {
  const order = sortOrder(field);
  if (order === "asc") return ArrowUpOutline;
  if (order === "desc") return ArrowDownOutline;
  return SwapVerticalOutline;
}

function sortButtonLabel(field: string): string {
  const order = sortOrder(field);
  if (order === "asc") return "Sorted ascending; click for descending";
  if (order === "desc") return "Sorted descending; click to clear sorting";
  return "Sort ascending";
}

function rowDefectId(row: VxeSampleTableRow | undefined): number | null {
  if (!row) return null;
  const id = Number(row.defect_id);
  return Number.isFinite(id) ? id : null;
}

function rowIsSelected(id: number): boolean {
  return allMatchingRowsSelected.value
    ? !selectionDeltaIds.value.has(id)
    : selectionDeltaIds.value.has(id);
}

const selectedCount = computed(() =>
  allMatchingRowsSelected.value
    ? Math.max(0, serverTotal.value - selectionDeltaIds.value.size)
    : selectionDeltaIds.value.size,
);

function emitSelection(): void {
  const ids = Array.from(selectionDeltaIds.value).sort((left, right) => left - right);
  emit(
    "selection-change",
    allMatchingRowsSelected.value ? { kind: "all", excludedIds: ids } : { kind: "ids", ids },
  );
}

function handleCheckboxChange(
  event: VxeTableDefines.CheckboxChangeEventParams<VxeSampleTableRow>,
): void {
  if (props.enableSelection !== true) return;
  if (!event.row) return;
  const id = rowDefectId(event.row);
  if (id === null) return;
  const next = new Set(selectionDeltaIds.value);
  if (allMatchingRowsSelected.value) {
    if (event.checked) next.delete(id);
    else next.add(id);
  } else if (event.checked) next.add(id);
  else next.delete(id);
  selectionDeltaIds.value = next;
  emitSelection();
}

function handleCheckboxAll(event: VxeTableDefines.CheckboxAllEventParams<VxeSampleTableRow>): void {
  if (props.enableSelection !== true) return;
  // The header represents every row matching the current server-side query,
  // not only VXE's loaded 250-row window. Keep it symbolic instead of
  // materializing every defect ID in the browser.
  allMatchingRowsSelected.value = event.checked;
  selectionDeltaIds.value = new Set();
  emitSelection();
}

function handleCellClick(event: VxeTableDefines.CellClickEventParams<VxeSampleTableRow>): void {
  if (props.enableSelection !== true) return;
  if (!event.row || event.column?.type === "checkbox") return;
  const id = rowDefectId(event.row);
  if (id === null) return;
  const next = new Set(selectionDeltaIds.value);
  const checked = !rowIsSelected(id);
  if (allMatchingRowsSelected.value) {
    if (checked) next.delete(id);
    else next.add(id);
  } else if (checked) next.add(id);
  else next.delete(id);
  selectionDeltaIds.value = next;
  void gridRef.value?.setCheckboxRowKey(id, checked);
  emitSelection();
}

function syncCurrentPageSelection(): void {
  for (const id of loadedDefectIds) {
    void gridRef.value?.setCheckboxRowKey(id, rowIsSelected(id));
  }
}

function clearSelection(): void {
  if (props.enableSelection !== true) return;
  allMatchingRowsSelected.value = false;
  selectionDeltaIds.value = new Set();
  void gridRef.value?.clearCheckboxRow();
  emitSelection();
}

function renderCell(definition: ColumnDefinition, row: VxeSampleTableRow | undefined): string {
  if (!row) return "";
  if (definition.key !== "defect_id" && !row._isHydrated) return "";
  if (definition.render) return definition.render(row);
  const value = row[definition.key];
  return value == null || value === "" ? "-" : String(value);
}

function sortOrder(field: string): VxeTablePropTypes.SortOrder {
  return tableSort.value?.field === field ? tableSort.value.direction : null;
}

async function refreshGridLayout(horizontalScrollLeft?: number): Promise<void> {
  await nextTick();
  const grid = gridRef.value;
  await grid?.recalculate(true);
  await grid?.refreshScroll();
  await syncGridToVirtualRail();
  if (horizontalScrollLeft !== undefined) {
    await grid?.scrollTo(horizontalScrollLeft, null);
  }
  syncScrollbarMetrics();
}

function syncScrollbarMetrics(): void {
  const xScroll = gridRef.value?.getScrollData();
  const yScroll = virtualRailRef.value;
  scrollbarMetrics.value = {
    xClientSize: xScroll?.clientWidth ?? 0,
    xScrollSize: xScroll?.scrollWidth ?? 0,
    xPosition: xScroll?.scrollLeft ?? 0,
    xTrackSize: xScrollbarRailRef.value?.clientWidth ?? 0,
    yClientSize: yScroll?.clientHeight ?? 0,
    yScrollSize: yScroll?.scrollHeight ?? 0,
    yPosition: yScroll?.scrollTop ?? 0,
    yTrackSize: yScrollbarRailRef.value?.clientHeight ?? 0,
  };
}

function setHorizontalScroll(scrollLeft: number): void {
  const { xClientSize, xScrollSize } = scrollbarMetrics.value;
  const nextScrollLeft = Math.max(0, Math.min(xScrollSize - xClientSize, scrollLeft));
  scrollbarMetrics.value = {
    ...scrollbarMetrics.value,
    xPosition: nextScrollLeft,
  };
  void Promise.resolve(gridRef.value?.scrollTo(nextScrollLeft, null)).then(syncScrollbarMetrics);
}

function setVerticalScroll(scrollTop: number): void {
  const rail = virtualRailRef.value;
  if (!rail) return;
  const maxScrollTop = Math.max(0, rail.scrollHeight - rail.clientHeight);
  rail.scrollTop = Math.max(0, Math.min(maxScrollTop, scrollTop));
  syncScrollbarMetrics();
  void syncGridToVirtualRail(rail);
}

function beginScrollbarDrag(axis: "x" | "y", event: MouseEvent): void {
  endScrollbarDrag();
  const metrics = scrollbarMetrics.value;
  const scrollableDistance =
    axis === "x"
      ? metrics.xScrollSize - metrics.xClientSize
      : metrics.yScrollSize - metrics.yClientSize;
  const trackDistance =
    axis === "x" ? metrics.xTrackSize - xThumbSize.value : metrics.yTrackSize - yThumbSize.value;
  if (scrollableDistance <= 0 || trackDistance <= 0) return;
  scrollbarDragState = {
    axis,
    startPointer: axis === "x" ? event.clientX : event.clientY,
    startScroll: axis === "x" ? metrics.xPosition : metrics.yPosition,
    scrollableDistance,
    trackDistance,
  };
  document.addEventListener("mousemove", handleScrollbarDrag);
  document.addEventListener("mouseup", endScrollbarDrag, { once: true });
}

function handleScrollbarDrag(event: MouseEvent): void {
  if (!scrollbarDragState) return;
  const pointer = scrollbarDragState.axis === "x" ? event.clientX : event.clientY;
  const delta = pointer - scrollbarDragState.startPointer;
  const position =
    scrollbarDragState.startScroll +
    (delta / scrollbarDragState.trackDistance) * scrollbarDragState.scrollableDistance;
  if (scrollbarDragState.axis === "x") {
    setHorizontalScroll(position);
  } else {
    setVerticalScroll(position);
  }
}

function endScrollbarDrag(): void {
  scrollbarDragState = null;
  document.removeEventListener("mousemove", handleScrollbarDrag);
}

function jumpScrollbar(axis: "x" | "y", event: MouseEvent): void {
  const target = event.currentTarget;
  if (!(target instanceof HTMLElement)) return;
  const rect = target.getBoundingClientRect();
  const metrics = scrollbarMetrics.value;
  if (axis === "x") {
    const trackDistance = metrics.xTrackSize - xThumbSize.value;
    if (trackDistance <= 0) return;
    const offset = event.clientX - rect.left - xThumbSize.value / 2;
    setHorizontalScroll((offset / trackDistance) * (metrics.xScrollSize - metrics.xClientSize));
    return;
  }
  const trackDistance = metrics.yTrackSize - yThumbSize.value;
  if (trackDistance <= 0) return;
  const offset = event.clientY - rect.top - yThumbSize.value / 2;
  setVerticalScroll((offset / trackDistance) * (metrics.yScrollSize - metrics.yClientSize));
}

function virtualScrollPosition(rail: HTMLElement): {
  page: number;
  localScrollTop: number;
} {
  const pageHeight = resolvedPageSize.value * ROW_HEIGHT;
  const page = pageHeight > 0 ? Math.floor(rail.scrollTop / pageHeight) : 0;
  return {
    page,
    localScrollTop: rail.scrollTop - page * pageHeight,
  };
}

async function syncGridToVirtualRail(rail = virtualRailRef.value): Promise<void> {
  if (!rail) return;
  const position = virtualScrollPosition(rail);
  requestedPage = position.page;
  if (renderedPage !== position.page) {
    await loadPage(position.page);
  }
  if (renderedPage !== position.page || requestedPage !== position.page) return;
  await gridRef.value?.scrollTo(null, position.localScrollTop);
}

function resetVirtualPosition(): void {
  requestedPage = 0;
  renderedPage = -1;
  const rail = virtualRailRef.value;
  if (rail) rail.scrollTop = 0;
  void gridRef.value?.scrollTo(null, 0);
  syncScrollbarMetrics();
}

function handleVirtualRailScroll(event: Event): void {
  syncScrollbarMetrics();
  void syncGridToVirtualRail(event.currentTarget as HTMLElement);
}

function handleGridScroll(): void {
  syncScrollbarMetrics();
}

function handleWheel(event: WheelEvent): void {
  const rail = virtualRailRef.value;
  if (!rail || Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
  const delta =
    event.deltaMode === 1
      ? event.deltaY * ROW_HEIGHT
      : event.deltaMode === 2
        ? event.deltaY * rail.clientHeight
        : event.deltaY;
  const maxScrollTop = Math.max(0, rail.scrollHeight - rail.clientHeight);
  const nextScrollTop = Math.max(0, Math.min(maxScrollTop, rail.scrollTop + delta));
  if (nextScrollTop === rail.scrollTop) return;
  event.preventDefault();
  setVerticalScroll(nextScrollTop);
}

watch(
  () => props.filter,
  (filter) => {
    const next = filter ?? {};
    if (JSON.stringify(next) === JSON.stringify(tableFilter.value)) return;
    tableFilter.value = { ...next };
  },
  { deep: true },
);

watch(
  () => props.sort,
  (sort) => {
    const next = normalizeTableSort(sort);
    if (JSON.stringify(next) === JSON.stringify(tableSort.value)) return;
    tableSort.value = next;
  },
  { deep: true },
);

watch(
  [() => props.dataSource.scopeKey, resolvedPageSize, tableFilter, tableSort],
  () => {
    void resetRows();
  },
  { deep: true, immediate: true },
);

watch(
  () => props.selection,
  (selection: ScTableSelectionConstraint | undefined) => {
    allMatchingRowsSelected.value = selection?.kind === "all";
    selectionDeltaIds.value = new Set(
      selection?.kind === "all" ? selection.excludedIds : (selection?.ids ?? []),
    );
    void nextTick(syncCurrentPageSelection);
  },
  { deep: true, immediate: true },
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
    void gridRef.value?.loadData(displayRows);
  }
  if (gridHostRef.value && typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver(() => {
      void nextTick(syncScrollbarMetrics);
    });
    resizeObserver.observe(gridHostRef.value);
  }
  void refreshGridLayout();
});

onBeforeUnmount(() => {
  requestVersion += 1;
  resizeObserver?.disconnect();
  resizeObserver = null;
  endScrollbarDrag();
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
    const row = rawRows.find((r) => Number(r?.defect_id) === defectId);
    if (
      !row?._isHydrated ||
      row.wafer_x == null ||
      row.wafer_y == null ||
      row.die_x == null ||
      row.die_y == null ||
      row.reticle_x == null ||
      row.reticle_y == null
    ) {
      return undefined;
    }
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
  <div
    class="sst-vxe"
    :data-arrow-rows="storageStats.length"
    :data-hydrated-rows="storageStats.hydratedRows"
    :data-row-objects="storageStats.rowObjectsCreated"
    @wheel="handleWheel"
  >
    <div class="sst-vxe-header">
      <NText depth="2" class="sst-vxe-header-label"> Sample Data ({{ serverTotal }}) </NText>
      <div class="sst-vxe-header-actions">
        <NButton
          v-if="enableSelection && selectedCount > 0"
          size="tiny"
          quaternary
          @click="clearSelection"
        >
          Clear Selection ({{ selectedCount }})
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
    <div ref="gridHostRef" class="sst-vxe-grid-host">
      <vxe-table
        ref="gridRef"
        class="sst-vxe-grid"
        border
        auto-resize
        show-overflow
        size="mini"
        height="100%"
        :loading="loading || (isFetching && serverTotal === 0)"
        :row-config="rowConfig"
        :cell-config="cellConfig"
        :header-cell-config="headerCellConfig"
        :checkbox-config="checkboxConfig"
        :virtual-y-config="virtualYConfig"
        :virtual-x-config="virtualXConfig"
        :scrollbar-config="scrollbarConfig"
        @checkbox-change="handleCheckboxChange"
        @checkbox-all="handleCheckboxAll"
        @cell-click="handleCellClick"
        @scroll="handleGridScroll"
      >
        <vxe-column v-if="enableSelection" type="checkbox" width="44" fixed="left" align="center" />
        <vxe-column
          v-for="definition in activeColumnDefinitions"
          :key="String(definition.key)"
          :field="String(definition.key)"
          :title="definition.title"
          :width="definition.width"
          :fixed="definition.key === 'defect_id' ? 'left' : undefined"
        >
          <template #header>
            <div class="sst-vxe-column-header">
              <span class="sst-vxe-column-title">{{ definition.title }}</span>
              <div class="sst-vxe-column-actions" @click.stop>
                <NButton
                  size="tiny"
                  quaternary
                  circle
                  class="sst-vxe-sort-button"
                  :class="{
                    'sst-vxe-sort-button--active': sortOrder(String(definition.key)) !== null,
                  }"
                  :aria-label="sortButtonLabel(String(definition.key))"
                  :title="sortButtonLabel(String(definition.key))"
                  @click="cycleSort(String(definition.key))"
                >
                  <template #icon>
                    <NIcon><component :is="sortIcon(String(definition.key))" /></NIcon>
                  </template>
                </NButton>
                <NPopover
                  :key="`${String(definition.key)}:${filterPopoverVersion}`"
                  trigger="click"
                  placement="bottom-start"
                  @update:show="openFilter(definition, $event)"
                >
                  <template #trigger>
                    <NButton
                      size="tiny"
                      quaternary
                      circle
                      class="sst-vxe-filter-button"
                      :class="{
                        'sst-vxe-filter-button--active': isColumnFiltered(String(definition.key)),
                      }"
                      :aria-label="`Filter ${definition.title}`"
                      :title="`Filter ${definition.title}`"
                    >
                      <template #icon>
                        <NIcon><FunnelOutline /></NIcon>
                      </template>
                    </NButton>
                  </template>
                  <ScTextFilterMenu
                    v-if="definition.key === 'defect_id'"
                    :applied-values="getSetFilterValues('defect_id')"
                    @apply="applySetFilter('defect_id', $event)"
                    @close="closeFilterPopover"
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
                    @close="closeFilterPopover"
                  />
                  <ScRangeFilterMenu
                    v-else
                    :min="getFilterState(String(definition.key)).min"
                    :max="getFilterState(String(definition.key)).max"
                    @update:min="getFilterState(String(definition.key)).min = $event"
                    @update:max="getFilterState(String(definition.key)).max = $event"
                    @apply="applyRangeFilter(String(definition.key))"
                    @clear="clearFilter(String(definition.key))"
                    @close="closeFilterPopover"
                  />
                </NPopover>
              </div>
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
      <div
        ref="virtualRailRef"
        class="sst-vxe-virtual-rail"
        aria-hidden="true"
        @scroll="handleVirtualRailScroll"
      >
        <div :style="{ height: `${serverTotal * ROW_HEIGHT}px` }" />
      </div>
      <div
        ref="yScrollbarRailRef"
        class="sst-vxe-scrollbar-rail sst-vxe-scrollbar-rail--y"
        role="scrollbar"
        aria-label="Sample table vertical scroll"
        aria-orientation="vertical"
        :aria-valuemax="Math.max(0, scrollbarMetrics.yScrollSize - scrollbarMetrics.yClientSize)"
        :aria-valuenow="scrollbarMetrics.yPosition"
        aria-valuemin="0"
        @mousedown.prevent="jumpScrollbar('y', $event)"
      >
        <div
          class="sst-vxe-scrollbar-thumb"
          :style="yThumbStyle"
          @mousedown.stop.prevent="beginScrollbarDrag('y', $event)"
        />
      </div>
      <div
        ref="xScrollbarRailRef"
        class="sst-vxe-scrollbar-rail sst-vxe-scrollbar-rail--x"
        role="scrollbar"
        aria-label="Sample table horizontal scroll"
        aria-orientation="horizontal"
        :aria-valuemax="Math.max(0, scrollbarMetrics.xScrollSize - scrollbarMetrics.xClientSize)"
        :aria-valuenow="scrollbarMetrics.xPosition"
        aria-valuemin="0"
        @mousedown.prevent="jumpScrollbar('x', $event)"
      >
        <div
          class="sst-vxe-scrollbar-thumb"
          :style="xThumbStyle"
          @mousedown.stop.prevent="beginScrollbarDrag('x', $event)"
        />
      </div>
    </div>

    <NText v-if="pageError" type="error" class="sst-vxe-error">
      {{ pageError }}
    </NText>
  </div>
</template>

<style scoped>
.sst-vxe {
  position: relative;
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

.sst-vxe-virtual-rail {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 10px;
  width: 10px;
  overflow-x: hidden;
  overflow-y: scroll;
  opacity: 0;
  pointer-events: none;
  scrollbar-width: none;
  z-index: 5;
}

.sst-vxe-virtual-rail::-webkit-scrollbar {
  width: 0;
  height: 0;
}

.sst-vxe-scrollbar-rail {
  position: absolute;
  z-index: 20;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.28);
  user-select: none;
  transition: none;
}

.sst-vxe-scrollbar-rail--y {
  top: 0;
  right: 0;
  bottom: 10px;
  width: 10px;
}

.sst-vxe-scrollbar-rail--x {
  right: 10px;
  bottom: 0;
  left: 0;
  height: 10px;
}

.sst-vxe-scrollbar-thumb {
  width: 100%;
  height: 100%;
  border-radius: 999px;
  background: rgba(142, 160, 255, 0.7);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.16);
  cursor: pointer;
  outline: none;
  transition: none;
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

.sst-vxe-grid-host {
  flex: 1;
  min-height: 0;
  min-width: 0;
  position: relative;
  overflow: hidden;
}

.sst-vxe-grid {
  height: 100%;
  width: 100%;
}

.sst-vxe-grid :deep(.vxe-table--scroll-x-handle) {
  opacity: 0;
  scrollbar-width: none;
}

.sst-vxe-grid :deep(.vxe-table--scroll-x-handle::-webkit-scrollbar) {
  width: 0;
  height: 0;
}

.sst-vxe-column-header {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

.sst-vxe-column-title {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sst-vxe-column-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 1px;
}

.sst-vxe-sort-button,
.sst-vxe-filter-button {
  --n-width: 20px !important;
  --n-height: 20px !important;
  font-size: 12px;
}

.sst-vxe-sort-button--active,
.sst-vxe-filter-button--active {
  color: var(--cv-primary, #36ad6a);
}

.sst-vxe-error {
  padding-top: 4px;
  font-size: 12px;
}

:deep(.vxe-cell) {
  line-height: 30px;
}
</style>
