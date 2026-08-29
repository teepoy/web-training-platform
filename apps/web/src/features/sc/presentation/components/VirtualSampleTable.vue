<script setup lang="ts">
import { computed, markRaw, onBeforeUnmount, ref, watch } from "vue";
import type { CSSProperties } from "vue";
import { useI18n } from "vue-i18n";
import { NButton, NIcon, NPopover, NText, NTooltip } from "naive-ui";
import { getCoreRowModel, useVueTable, type ColumnDef } from "@tanstack/vue-table";
import { useVirtualizer } from "@tanstack/vue-virtual";
import {
  ArrowDownOutline,
  ArrowUpOutline,
  CloseCircleOutline,
  DownloadOutline,
  FunnelOutline,
  SwapVerticalOutline,
} from "@vicons/ionicons5";
import type { ScSampleTableFilter, ScSampleTableSort } from "@/features/sc/domain/sampleTable";
import type {
  ScDataColumn,
  ScTableSelectionConstraint,
} from "@/features/sc/domain/workbenchDataSource";
import type { ScSampleTableDataSource } from "@/features/sc/domain/workbenchInteraction";
import { SC_SCROLL_QUERY_DEBOUNCE_MS } from "../composables/scrollQueryDebounce";
import { formatNumber } from "@/shared/i18n/format";
import RangeFilterMenu from "@/shared/components/table-filter/RangeFilterMenu.vue";
import SetFilterMenu from "@/shared/components/table-filter/SetFilterMenu.vue";
import DefectIdFilterMenu from "./DefectIdFilterMenu.vue";

const { t } = useI18n();
import {
  normalizeSampleTableFilterValue,
  renderSampleTableCell,
  sampleTablePresentationColumns,
  sampleTableRowDefectId,
  sampleTableRowKey,
  type ScSampleTablePresentationColumn,
  type ScSampleTablePresentationRow,
} from "./sampleTablePresentation";
import {
  downloadSampleTableCsv,
  exportSampleTableCsv,
  type SampleTableCsvProgress,
} from "./sampleTableCsvExport";
import type { ScSampleTableBaseProps, ScSampleTableEmits } from "./scSampleTableContract";

interface ScSampleTableTanStackProps extends ScSampleTableBaseProps {
  dataSource: ScSampleTableDataSource;
  defectIds?: string[];
  pageSize?: number;
}

interface VirtualColumnItem {
  index: number;
  key: string | number;
  size: number;
  start: number;
}

const props = defineProps<ScSampleTableTanStackProps>();
const emit = defineEmits<ScSampleTableEmits>();

const PAGE_SIZE = 50;
const ROW_HEIGHT = 36;
const HEADER_HEIGHT = 36;
const PAGE_WINDOW_OVERSCAN_ROWS = 8;
const COLUMN_OVERSCAN = 3;
const SELECTION_COLUMN_ID = "__selection";
const SELECTION_COLUMN_WIDTH = 44;
const DEFAULT_TABLE_SORT: ScSampleTableSort = {
  field: "defect_id",
  direction: "asc",
};

const scrollRef = ref<HTMLElement | null>(null);
const sourceColumns = ref<ScDataColumn[] | null>(null);
const loadedRows = ref<ScSampleTablePresentationRow[]>([]);
const loadedStart = ref(0);
const serverTotal = ref(0);
const pageError = ref<string | null>(null);
const streamStatus = ref("");
const isFetching = ref(false);
const tableFilter = ref<ScSampleTableFilter>({ ...(props.filter ?? {}) });
const tableSort = ref<ScSampleTableSort>(normalizeTableSort(props.sort));
const selectionDeltaIds = ref<Set<string>>(new Set());
const allMatchingRowsSelected = ref(false);
const filterPopoverVersion = ref(0);
const filterState = ref<Record<string, { min: number | null; max: number | null }>>({});
const setFilterSearch = ref<Record<string, string>>({});
const setFilterDraft = ref<Record<string, Set<string>>>({});
const discoveredSetFilterValues = ref<Record<string, Array<string | number>>>({});
const searchedSetFilterValues = ref<Record<string, Array<string | number>>>({});
const setFilterSearchLoading = ref<Record<string, boolean>>({});
const isExportingCsv = ref(false);
const csvExportProgress = ref<SampleTableCsvProgress | null>(null);
const csvExportStatus = ref("");
const csvExportError = ref("");

let requestVersion = 0;
let requestedStart = 0;
let loadingRequest: { start: number; version: number } | null = null;
let loadController: AbortController | null = null;
let loadTimer: ReturnType<typeof setTimeout> | null = null;
let sourceColumnsRequestVersion = 0;
let csvExportController: AbortController | null = null;

const resolvedPageSize = computed(() => props.pageSize ?? PAGE_SIZE);
const activeColumnDefinitions = computed(() =>
  sampleTablePresentationColumns(sourceColumns.value, props.showReclassifyColumns === true),
);
const definitionsByKey = computed(
  () => new Map(activeColumnDefinitions.value.map((definition) => [definition.key, definition])),
);

const tanstackColumns = computed<ColumnDef<ScSampleTablePresentationRow>[]>(() => {
  const definitions: ColumnDef<ScSampleTablePresentationRow>[] = [];
  if (props.enableSelection === true) {
    definitions.push({
      id: SELECTION_COLUMN_ID,
      header: t("sc.select"),
      size: SELECTION_COLUMN_WIDTH,
    });
  }
  for (const definition of activeColumnDefinitions.value) {
    definitions.push({
      id: definition.key,
      accessorFn: (row) => row[definition.key],
      header: definition.title,
      size: definition.width,
    });
  }
  return definitions;
});

const table = useVueTable({
  get data() {
    return loadedRows.value;
  },
  get columns() {
    return tanstackColumns.value;
  },
  getCoreRowModel: getCoreRowModel(),
  getRowId: (row) => row.row_key,
  manualFiltering: true,
  manualSorting: true,
});

const selectionColumn = computed(() =>
  table.getAllLeafColumns().find((column) => column.id === SELECTION_COLUMN_ID),
);
const defectColumn = computed(() =>
  table.getAllLeafColumns().find((column) => column.id === "defect_id"),
);
const scrollColumns = computed(() =>
  table
    .getVisibleLeafColumns()
    .filter((column) => column.id !== SELECTION_COLUMN_ID && column.id !== "defect_id"),
);
const pinnedWidth = computed(
  () => (selectionColumn.value?.getSize() ?? 0) + (defectColumn.value?.getSize() ?? 0),
);

const rowVirtualizer = useVirtualizer({
  get count() {
    return serverTotal.value;
  },
  getScrollElement: () => scrollRef.value,
  estimateSize: () => ROW_HEIGHT,
  overscan: PAGE_WINDOW_OVERSCAN_ROWS,
  getItemKey: (index) => index,
});

const columnVirtualizer = useVirtualizer({
  get count() {
    return scrollColumns.value.length;
  },
  getScrollElement: () => scrollRef.value,
  estimateSize: (index) => scrollColumns.value[index]?.getSize() ?? 120,
  getItemKey: (index) => scrollColumns.value[index]?.id ?? index,
  horizontal: true,
  get paddingStart() {
    return pinnedWidth.value;
  },
  overscan: COLUMN_OVERSCAN,
});

const virtualRows = computed(() => rowVirtualizer.value.getVirtualItems());
const virtualColumns = computed(
  () => columnVirtualizer.value.getVirtualItems() as VirtualColumnItem[],
);
const totalRowsHeight = computed(() => rowVirtualizer.value.getTotalSize());
const totalColumnsWidth = computed(() => columnVirtualizer.value.getTotalSize());
const tableWidthStyle = computed<CSSProperties>(() => ({
  width: `${Math.max(totalColumnsWidth.value, pinnedWidth.value)}px`,
  minWidth: "100%",
}));
const tableHeaderStyle = computed<CSSProperties>(() => ({
  ...tableWidthStyle.value,
  display: "flex",
}));
const tableBodyStyle = computed<CSSProperties>(() => ({
  ...tableWidthStyle.value,
  height: `${totalRowsHeight.value}px`,
}));

const selectedCount = computed(() =>
  allMatchingRowsSelected.value
    ? Math.max(0, serverTotal.value - selectionDeltaIds.value.size)
    : selectionDeltaIds.value.size,
);
const allRowsChecked = computed(
  () => allMatchingRowsSelected.value && selectionDeltaIds.value.size === 0,
);
const someRowsChecked = computed(() => selectedCount.value > 0 && !allRowsChecked.value);

function normalizeTableSort(sort: ScSampleTableSort | null | undefined): ScSampleTableSort {
  return sort ?? DEFAULT_TABLE_SORT;
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

function definitionForColumn(columnId: string): ScSampleTablePresentationColumn | undefined {
  return definitionsByKey.value.get(columnId);
}

function rowAt(globalIndex: number): ScSampleTablePresentationRow | undefined {
  const localIndex = globalIndex - loadedStart.value;
  return localIndex >= 0 && localIndex < loadedRows.value.length
    ? loadedRows.value[localIndex]
    : undefined;
}

function rowStyle(start: number): CSSProperties {
  return {
    ...tableWidthStyle.value,
    display: "flex",
    height: `${ROW_HEIGHT}px`,
    transform: `translateY(${start}px)`,
  };
}

function virtualColumnStyle(item: VirtualColumnItem): CSSProperties {
  return {
    left: `${item.start}px`,
    width: `${item.size}px`,
  };
}

function selectionCellStyle(): CSSProperties {
  return {
    left: "0px",
    width: `${selectionColumn.value?.getSize() ?? 0}px`,
  };
}

function defectCellStyle(): CSSProperties {
  return {
    left: `${selectionColumn.value?.getSize() ?? 0}px`,
    width: `${defectColumn.value?.getSize() ?? 0}px`,
  };
}

async function loadSourceColumns(): Promise<void> {
  const version = ++sourceColumnsRequestVersion;
  const source = props.dataSource;
  const scopeKey = source.scopeKey;
  try {
    const columns = (await source.loadColumns?.()) ?? null;
    if (version === sourceColumnsRequestVersion && scopeKey === props.dataSource.scopeKey) {
      sourceColumns.value = columns;
    }
  } catch (error) {
    if (version !== sourceColumnsRequestVersion || scopeKey !== props.dataSource.scopeKey) return;
    pageError.value = error instanceof Error ? error.message : t("sc.sampleColumnsLoadFailed");
  }
}

function visibleRowCount(): number {
  return Math.max(1, Math.ceil((scrollRef.value?.clientHeight ?? ROW_HEIGHT) / ROW_HEIGHT));
}

function requestEnd(start: number): number {
  return start + resolvedPageSize.value + visibleRowCount() + PAGE_WINDOW_OVERSCAN_ROWS;
}

async function loadPage(start: number): Promise<void> {
  if (start < 0 || (loadingRequest?.start === start && loadingRequest.version === requestVersion)) {
    return;
  }
  if (serverTotal.value > 0 && start >= serverTotal.value) return;

  const version = requestVersion;
  const request = { start, version };
  loadController?.abort();
  const controller = new AbortController();
  loadController = controller;
  loadingRequest = request;
  pageError.value = null;
  isFetching.value = true;
  if (start === 0 && loadedRows.value.length === 0) streamStatus.value = t("sc.loadingSampleRows");

  try {
    const page = await props.dataSource.loadRows({
      defectIds: props.defectIds ?? [],
      anchor: String(start),
      limit: requestEnd(start) - start,
      filter: tableFilter.value,
      sort: tableSort.value,
      signal: controller.signal,
    });
    if (version !== requestVersion || start !== requestedStart) return;
    loadedStart.value = start;
    loadedRows.value = page.items.map((item) =>
      markRaw({ ...item, _isHydrated: true } as ScSampleTablePresentationRow),
    );
    serverTotal.value = page.total;
    accumulateDiscoveredSetFilterValues(loadedRows.value);
  } catch (error) {
    if (!isAbortError(error) && version === requestVersion) {
      pageError.value = error instanceof Error ? error.message : t("sc.sampleRowsLoadFailed");
    }
  } finally {
    if (loadController === controller) loadController = null;
    if (loadingRequest === request) loadingRequest = null;
    if (version === requestVersion && loadingRequest === null) {
      isFetching.value = false;
      streamStatus.value = "";
    }
  }
}

function cancelQueuedLoad(): void {
  if (loadTimer === null) return;
  clearTimeout(loadTimer);
  loadTimer = null;
}

function queueVisibleRangeLoad(): void {
  const items = virtualRows.value;
  if (items.length === 0) return;
  const first = items[0]?.index ?? 0;
  const last = items.at(-1)?.index ?? first;
  const loadedEnd = loadedStart.value + loadedRows.value.length;
  if (first >= loadedStart.value && last < loadedEnd) {
    cancelQueuedLoad();
    return;
  }

  const start = Math.floor(first / resolvedPageSize.value) * resolvedPageSize.value;
  requestedStart = start;
  if (loadingRequest && loadingRequest.start !== start) loadController?.abort();
  cancelQueuedLoad();
  loadTimer = setTimeout(() => {
    loadTimer = null;
    if (requestedStart !== start) return;
    void loadPage(start);
  }, SC_SCROLL_QUERY_DEBOUNCE_MS);
}

async function resetRows(): Promise<void> {
  requestVersion += 1;
  requestedStart = 0;
  loadController?.abort();
  loadingRequest = null;
  cancelQueuedLoad();
  loadedStart.value = 0;
  loadedRows.value = [];
  serverTotal.value = 0;
  pageError.value = null;
  isFetching.value = true;
  streamStatus.value = t("sc.loadingSampleRows");
  if (scrollRef.value) scrollRef.value.scrollTop = 0;
  await loadPage(0);
}

function accumulateDiscoveredSetFilterValues(items: ScSampleTablePresentationRow[]): void {
  for (const definition of activeColumnDefinitions.value) {
    if (definition.filter !== "set") continue;
    const field = definition.key;
    const values = new Map(
      (discoveredSetFilterValues.value[field] ?? []).map((value) => {
        const normalized = normalizeSampleTableFilterValue(field, value);
        return [String(normalized), normalized];
      }),
    );
    for (const row of items) {
      const value = row[field];
      if (typeof value === "string" || typeof value === "number") {
        const normalized = normalizeSampleTableFilterValue(field, value);
        values.set(String(normalized), normalized);
      }
    }
    discoveredSetFilterValues.value[field] = Array.from(values.values());
  }
}

function getFilterState(field: string): { min: number | null; max: number | null } {
  if (!filterState.value[field]) filterState.value[field] = { min: null, max: null };
  return filterState.value[field];
}

function getSetFilterValues(field: string): Array<string | number> {
  const filter = tableFilter.value[field];
  return filter?.filterType === "set"
    ? filter.values.map((value) => normalizeSampleTableFilterValue(field, value))
    : [];
}

function getSetFilterOptions(definition: ScSampleTablePresentationColumn) {
  const field = definition.key;
  const values = new Map<string, string | number>();
  for (const value of searchedSetFilterValues.value[field] ?? []) {
    const normalized = normalizeSampleTableFilterValue(field, value);
    values.set(String(normalized), normalized);
  }
  for (const value of discoveredSetFilterValues.value[field] ?? []) {
    const normalized = normalizeSampleTableFilterValue(field, value);
    values.set(String(normalized), normalized);
  }
  for (const value of getSetFilterValues(field)) {
    const normalized = normalizeSampleTableFilterValue(field, value);
    values.set(String(normalized), normalized);
  }
  return Array.from(values.values())
    .sort((left, right) =>
      typeof left === "number" && typeof right === "number"
        ? left - right
        : String(left).localeCompare(String(right), undefined, { numeric: true }),
    )
    .map((value) => ({ label: String(value), value }));
}

async function searchSetFilterOptions(field: string): Promise<void> {
  setFilterSearchLoading.value = { ...setFilterSearchLoading.value, [field]: true };
  try {
    searchedSetFilterValues.value = {
      ...searchedSetFilterValues.value,
      [field]:
        (await props.dataSource.loadDistinctValues?.({
          field,
          search: setFilterSearch.value[field] ?? "",
          limit: 200,
          filter: tableFilter.value,
          sort: tableSort.value,
        })) ?? [],
    };
  } finally {
    setFilterSearchLoading.value = { ...setFilterSearchLoading.value, [field]: false };
  }
}

function applySetFilter(field: string, values: Array<string | number>): void {
  const next = { ...tableFilter.value };
  if (values.length === 0) delete next[field];
  else {
    next[field] = {
      filterType: "set",
      values: values.map((value) => normalizeSampleTableFilterValue(field, value)),
    };
  }
  tableFilter.value = next;
  emit("filter-change", next);
  filterPopoverVersion.value += 1;
}

function applyRangeFilter(field: string): void {
  const state = filterState.value[field];
  if (!state) return;
  if (state.min === null && state.max === null) {
    const next = { ...tableFilter.value };
    delete next[field];
    tableFilter.value = next;
  } else {
    if (state.min === null || state.max === null || state.min > state.max) return;
    tableFilter.value = {
      ...tableFilter.value,
      [field]: {
        filterType: "number",
        type: "inRange",
        filter: state.min,
        filterTo: state.max,
      },
    };
  }
  emit("filter-change", tableFilter.value);
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

function openFilter(definition: ScSampleTablePresentationColumn, open: boolean): void {
  if (!open) {
    filterPopoverVersion.value += 1;
    return;
  }
  if (definition.filter === "set") {
    setFilterSearch.value[definition.key] = "";
    setFilterDraft.value[definition.key] = new Set(getSetFilterValues(definition.key).map(String));
    return;
  }
  const applied = tableFilter.value[definition.key];
  filterState.value[definition.key] =
    applied?.filterType === "number"
      ? { min: applied.filter, max: applied.filterTo }
      : { min: null, max: null };
}

function closeFilterPopover(): void {
  filterPopoverVersion.value += 1;
}

function isColumnFiltered(field: string): boolean {
  return Boolean(tableFilter.value[field]);
}

function sortOrder(field: string): "asc" | "desc" | null {
  return tableSort.value.field === field ? tableSort.value.direction : null;
}

function cycleSort(field: string): void {
  const current = sortOrder(field);
  const next = current === null ? "asc" : current === "asc" ? "desc" : null;
  tableSort.value = next ? { field, direction: next } : DEFAULT_TABLE_SORT;
  emit("sort-change", { field, direction: next });
}

function sortIcon(field: string) {
  const order = sortOrder(field);
  if (order === "asc") return ArrowUpOutline;
  if (order === "desc") return ArrowDownOutline;
  return SwapVerticalOutline;
}

function sortButtonLabel(field: string): string {
  const order = sortOrder(field);
  if (order === "asc") return t("sc.sortedAscending");
  if (order === "desc") return t("sc.sortedDescending");
  return t("sc.sortAscending");
}

function rowIsSelected(id: string): boolean {
  return allMatchingRowsSelected.value
    ? !selectionDeltaIds.value.has(id)
    : selectionDeltaIds.value.has(id);
}

function emitSelection(): void {
  const ids = Array.from(selectionDeltaIds.value);
  emit(
    "selection-change",
    allMatchingRowsSelected.value ? { kind: "all", excludedIds: ids } : { kind: "ids", ids },
  );
}

function handleSelectAll(event: Event): void {
  if (props.enableSelection !== true) return;
  const target = event.currentTarget;
  if (!(target instanceof HTMLInputElement)) return;
  allMatchingRowsSelected.value = target.checked;
  selectionDeltaIds.value = new Set();
  emitSelection();
}

function toggleRowSelection(row: ScSampleTablePresentationRow | undefined): void {
  if (props.enableSelection !== true) return;
  const id = sampleTableRowKey(row);
  if (id === null) return;
  const checked = !rowIsSelected(id);
  const next = new Set(selectionDeltaIds.value);
  if (allMatchingRowsSelected.value) {
    if (checked) next.delete(id);
    else next.add(id);
  } else if (checked) next.add(id);
  else next.delete(id);
  selectionDeltaIds.value = next;
  emitSelection();
}

function handleRowCheckbox(row: ScSampleTablePresentationRow | undefined, event: Event): void {
  event.stopPropagation();
  toggleRowSelection(row);
}

function clearSelection(): void {
  if (props.enableSelection !== true) return;
  allMatchingRowsSelected.value = false;
  selectionDeltaIds.value = new Set();
  emitSelection();
}

function snapshotFilter(filter: ScSampleTableFilter): ScSampleTableFilter {
  return Object.fromEntries(
    Object.entries(filter).map(([field, value]) => [
      field,
      value.filterType === "set" ? { ...value, values: [...value.values] } : { ...value },
    ]),
  );
}

async function exportCsv(): Promise<void> {
  if (isExportingCsv.value || activeColumnDefinitions.value.length === 0) return;
  const controller = new AbortController();
  csvExportController = controller;
  isExportingCsv.value = true;
  csvExportProgress.value = null;
  csvExportStatus.value = "";
  csvExportError.value = "";
  try {
    const result = await exportSampleTableCsv({
      dataSource: props.dataSource,
      columns: activeColumnDefinitions.value,
      defectIds: [...(props.defectIds ?? [])],
      filter: snapshotFilter(tableFilter.value),
      sort: { ...tableSort.value },
      signal: controller.signal,
      onProgress: (progress) => {
        csvExportProgress.value = progress;
      },
    });
    downloadSampleTableCsv(
      result.blob,
      props.exportFileName ?? `${props.dataSource.scopeKey}-sample-data`,
    );
    csvExportStatus.value = t("sc.exportedRows", { count: formatNumber(result.total) });
  } catch (error) {
    if (!isAbortError(error)) {
      csvExportError.value = error instanceof Error ? error.message : t("sc.csvExportFailed");
    }
  } finally {
    if (csvExportController === controller) csvExportController = null;
    isExportingCsv.value = false;
  }
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
  () => void resetRows(),
  { deep: true, immediate: true },
);

watch(
  () => props.dataSource.scopeKey,
  () => void loadSourceColumns(),
  { immediate: true },
);

watch(
  () => props.selection,
  (selection: ScTableSelectionConstraint | undefined) => {
    allMatchingRowsSelected.value = selection?.kind === "all";
    selectionDeltaIds.value = new Set(
      selection?.kind === "all" ? selection.excludedIds : (selection?.ids ?? []),
    );
  },
  { deep: true, immediate: true },
);

watch(
  tableFilter,
  (filter) => {
    for (const definition of activeColumnDefinitions.value) {
      const value = filter[definition.key];
      filterState.value[definition.key] =
        value?.filterType === "number" && value.type === "inRange"
          ? { min: value.filter, max: value.filterTo }
          : { min: null, max: null };
    }
  },
  { immediate: true, deep: true },
);

watch(() => {
  const items = virtualRows.value;
  return `${items[0]?.index ?? -1}:${items.at(-1)?.index ?? -1}`;
}, queueVisibleRangeLoad);

onBeforeUnmount(() => {
  requestVersion += 1;
  loadController?.abort();
  loadController = null;
  cancelQueuedLoad();
  csvExportController?.abort();
  csvExportController = null;
});

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
    const row = loadedRows.value.find((item) => Number(item.defect_id) === defectId);
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
    class="sst-tanstack"
    data-sample-table-implementation="tanstack"
    :data-loaded-start="loadedStart"
    :data-loaded-rows="loadedRows.length"
  >
    <div class="sst-tanstack-toolbar">
      <NText depth="2" class="sst-tanstack-toolbar-label">{{
        t("sc.sampleData", { count: formatNumber(serverTotal) })
      }}</NText>
      <div class="sst-tanstack-toolbar-actions">
        <NTooltip v-if="enableSelection && selectedCount > 0" trigger="hover">
          <template #trigger>
            <NButton
              size="tiny"
              quaternary
              circle
              type="primary"
              :aria-label="`${t('common.clearSelection')} (${selectedCount})`"
              data-testid="clear-sample-selection"
              @click="clearSelection"
            >
              <template #icon
                ><NIcon><CloseCircleOutline /></NIcon
              ></template>
            </NButton>
          </template>
          {{ t("common.clearSelection") }} ({{ selectedCount }})
        </NTooltip>
        <NTooltip trigger="hover">
          <template #trigger>
            <NButton
              size="tiny"
              quaternary
              circle
              :aria-label="t('sc.exportSampleCsv')"
              :loading="isExportingCsv"
              :disabled="serverTotal === 0 || activeColumnDefinitions.length === 0"
              data-testid="export-sample-data-csv"
              @click="exportCsv"
            >
              <template #icon
                ><NIcon><DownloadOutline /></NIcon
              ></template>
            </NButton>
          </template>
          {{ t("sc.exportSampleCsv") }}
        </NTooltip>
        <NButton
          v-if="Object.keys(tableFilter).length > 0"
          size="tiny"
          quaternary
          @click="clearAllFilters"
        >
          {{ t("common.clearFilters", { count: Object.keys(tableFilter).length }) }}
        </NButton>
        <NText v-if="streamStatus" depth="3" class="sst-tanstack-status-info">
          {{ streamStatus }}
        </NText>
        <NText
          v-else-if="isExportingCsv && csvExportProgress"
          depth="3"
          class="sst-tanstack-status-info"
        >
          {{
            t("sc.exportProgress", {
              completed: formatNumber(csvExportProgress.completed),
              total: formatNumber(csvExportProgress.total),
            })
          }}
        </NText>
        <NText v-else-if="csvExportStatus" depth="3" class="sst-tanstack-status-info">
          {{ csvExportStatus }}
        </NText>
      </div>
    </div>

    <div
      ref="scrollRef"
      class="sst-tanstack-scroll"
      data-testid="sc-sample-table-scroll"
      tabindex="0"
    >
      <div class="sst-tanstack-header" :style="tableHeaderStyle" role="row">
        <div
          v-if="selectionColumn"
          class="sst-tanstack-cell sst-tanstack-cell--header sst-tanstack-cell--pinned"
          :style="selectionCellStyle()"
          role="columnheader"
        >
          <input
            class="sst-tanstack-checkbox"
            type="checkbox"
            :aria-label="t('sc.selectAllSampleRows')"
            :checked="allRowsChecked"
            :indeterminate="someRowsChecked"
            @change="handleSelectAll"
          />
        </div>
        <div
          v-if="defectColumn && definitionForColumn('defect_id')"
          class="sst-tanstack-cell sst-tanstack-cell--header sst-tanstack-cell--pinned sst-tanstack-cell--defect"
          :style="defectCellStyle()"
          role="columnheader"
        >
          <div class="sst-tanstack-column-header">
            <span class="sst-tanstack-column-title">
              {{ definitionForColumn("defect_id")?.title }}
            </span>
            <div class="sst-tanstack-column-actions" @click.stop>
              <NButton
                size="tiny"
                quaternary
                circle
                class="sst-tanstack-sort-button"
                :class="{ 'sst-tanstack-sort-button--active': sortOrder('defect_id') !== null }"
                :aria-label="sortButtonLabel('defect_id')"
                @click="cycleSort('defect_id')"
              >
                <template #icon>
                  <NIcon><component :is="sortIcon('defect_id')" /></NIcon>
                </template>
              </NButton>
              <NPopover
                :key="`defect_id:${filterPopoverVersion}`"
                trigger="click"
                placement="bottom-start"
                @update:show="openFilter(definitionForColumn('defect_id')!, $event)"
              >
                <template #trigger>
                  <NButton
                    size="tiny"
                    quaternary
                    circle
                    class="sst-tanstack-filter-button"
                    :class="{ 'sst-tanstack-filter-button--active': isColumnFiltered('defect_id') }"
                    :aria-label="t('sc.filterDefectId')"
                  >
                    <template #icon
                      ><NIcon><FunnelOutline /></NIcon
                    ></template>
                  </NButton>
                </template>
                <DefectIdFilterMenu
                  :applied-values="getSetFilterValues('defect_id')"
                  @apply="applySetFilter('defect_id', $event)"
                  @close="closeFilterPopover"
                />
              </NPopover>
            </div>
          </div>
        </div>

        <template v-for="virtualColumn in virtualColumns" :key="String(virtualColumn.key)">
          <div
            v-if="definitionForColumn(scrollColumns[virtualColumn.index]?.id ?? '')"
            class="sst-tanstack-cell sst-tanstack-cell--header"
            :style="virtualColumnStyle(virtualColumn)"
            role="columnheader"
          >
            <div class="sst-tanstack-column-header">
              <span class="sst-tanstack-column-title">
                {{ definitionForColumn(scrollColumns[virtualColumn.index]?.id ?? "")?.title }}
              </span>
              <div class="sst-tanstack-column-actions" @click.stop>
                <NButton
                  v-if="
                    definitionForColumn(scrollColumns[virtualColumn.index]?.id ?? '')?.filter !==
                    null
                  "
                  size="tiny"
                  quaternary
                  circle
                  class="sst-tanstack-sort-button"
                  :class="{
                    'sst-tanstack-sort-button--active':
                      sortOrder(scrollColumns[virtualColumn.index]?.id ?? '') !== null,
                  }"
                  :aria-label="sortButtonLabel(scrollColumns[virtualColumn.index]?.id ?? '')"
                  @click="cycleSort(scrollColumns[virtualColumn.index]?.id ?? '')"
                >
                  <template #icon>
                    <NIcon>
                      <component :is="sortIcon(scrollColumns[virtualColumn.index]?.id ?? '')" />
                    </NIcon>
                  </template>
                </NButton>
                <NPopover
                  v-if="
                    definitionForColumn(scrollColumns[virtualColumn.index]?.id ?? '')?.filter !==
                    null
                  "
                  :key="`${scrollColumns[virtualColumn.index]?.id}:${filterPopoverVersion}`"
                  trigger="click"
                  placement="bottom-start"
                  @update:show="
                    openFilter(
                      definitionForColumn(scrollColumns[virtualColumn.index]?.id ?? '')!,
                      $event,
                    )
                  "
                >
                  <template #trigger>
                    <NButton
                      size="tiny"
                      quaternary
                      circle
                      class="sst-tanstack-filter-button"
                      :class="{
                        'sst-tanstack-filter-button--active': isColumnFiltered(
                          scrollColumns[virtualColumn.index]?.id ?? '',
                        ),
                      }"
                      :aria-label="
                        t('sc.filterColumn', {
                          column:
                            definitionForColumn(scrollColumns[virtualColumn.index]?.id ?? '')
                              ?.title ?? '',
                        })
                      "
                    >
                      <template #icon
                        ><NIcon><FunnelOutline /></NIcon
                      ></template>
                    </NButton>
                  </template>
                  <SetFilterMenu
                    v-if="
                      definitionForColumn(scrollColumns[virtualColumn.index]?.id ?? '')?.filter ===
                      'set'
                    "
                    :search="setFilterSearch[scrollColumns[virtualColumn.index]?.id ?? ''] ?? ''"
                    :applied-values="
                      getSetFilterValues(scrollColumns[virtualColumn.index]?.id ?? '')
                    "
                    :draft-values="
                      Array.from(setFilterDraft[scrollColumns[virtualColumn.index]?.id ?? ''] ?? [])
                    "
                    :options="
                      getSetFilterOptions(
                        definitionForColumn(scrollColumns[virtualColumn.index]?.id ?? '')!,
                      )
                    "
                    @update:search="
                      setFilterSearch[scrollColumns[virtualColumn.index]?.id ?? ''] = $event
                    "
                    @update:draft-values="
                      setFilterDraft[scrollColumns[virtualColumn.index]?.id ?? ''] = new Set($event)
                    "
                    @search-options="
                      searchSetFilterOptions(scrollColumns[virtualColumn.index]?.id ?? '')
                    "
                    @apply="applySetFilter(scrollColumns[virtualColumn.index]?.id ?? '', $event)"
                    @close="closeFilterPopover"
                  />
                  <RangeFilterMenu
                    v-else
                    :min="getFilterState(scrollColumns[virtualColumn.index]?.id ?? '').min"
                    :max="getFilterState(scrollColumns[virtualColumn.index]?.id ?? '').max"
                    @update:min="
                      getFilterState(scrollColumns[virtualColumn.index]?.id ?? '').min = $event
                    "
                    @update:max="
                      getFilterState(scrollColumns[virtualColumn.index]?.id ?? '').max = $event
                    "
                    @apply="applyRangeFilter(scrollColumns[virtualColumn.index]?.id ?? '')"
                    @close="closeFilterPopover"
                  />
                </NPopover>
              </div>
            </div>
          </div>
        </template>
      </div>

      <div class="sst-tanstack-body" :style="tableBodyStyle" role="rowgroup">
        <div
          v-for="virtualRow in virtualRows"
          :key="String(virtualRow.key)"
          class="sst-tanstack-row"
          :class="{ 'sst-tanstack-row--placeholder': !rowAt(virtualRow.index) }"
          :style="rowStyle(virtualRow.start)"
          role="row"
          @click="toggleRowSelection(rowAt(virtualRow.index))"
        >
          <div
            v-if="selectionColumn"
            class="sst-tanstack-cell sst-tanstack-cell--pinned"
            :style="selectionCellStyle()"
            role="cell"
          >
            <input
              v-if="sampleTableRowKey(rowAt(virtualRow.index)) !== null"
              class="sst-tanstack-checkbox"
              type="checkbox"
              :aria-label="
                t('sc.selectSample', { sample: rowAt(virtualRow.index)?.defect_id ?? '' })
              "
              :checked="rowIsSelected(sampleTableRowKey(rowAt(virtualRow.index))!)"
              @click.stop
              @change="handleRowCheckbox(rowAt(virtualRow.index), $event)"
            />
          </div>
          <div
            v-if="defectColumn && definitionForColumn('defect_id')"
            class="sst-tanstack-cell sst-tanstack-cell--pinned sst-tanstack-cell--defect"
            :style="defectCellStyle()"
            role="cell"
          >
            {{ renderSampleTableCell(definitionForColumn("defect_id")!, rowAt(virtualRow.index)) }}
          </div>
          <div
            v-for="virtualColumn in virtualColumns"
            :key="String(virtualColumn.key)"
            class="sst-tanstack-cell"
            :style="virtualColumnStyle(virtualColumn)"
            :title="
              definitionForColumn(scrollColumns[virtualColumn.index]?.id ?? '')
                ? renderSampleTableCell(
                    definitionForColumn(scrollColumns[virtualColumn.index]?.id ?? '')!,
                    rowAt(virtualRow.index),
                  )
                : ''
            "
            role="cell"
          >
            {{
              definitionForColumn(scrollColumns[virtualColumn.index]?.id ?? "")
                ? renderSampleTableCell(
                    definitionForColumn(scrollColumns[virtualColumn.index]?.id ?? "")!,
                    rowAt(virtualRow.index),
                  )
                : ""
            }}
          </div>
        </div>
      </div>

      <div v-if="isFetching && loadedRows.length === 0" class="sst-tanstack-empty">
        <NText depth="3">{{ t("sc.loadingSampleRows") }}</NText>
      </div>
      <div v-else-if="!isFetching && serverTotal === 0" class="sst-tanstack-empty">
        <NText depth="3">{{ pageError ?? t("sc.noSampleRows") }}</NText>
      </div>
    </div>

    <NText v-if="pageError" type="error" class="sst-tanstack-error">
      {{ pageError }}
    </NText>
    <NText v-if="csvExportError" type="error" class="sst-tanstack-error">
      {{ csvExportError }}
    </NText>
  </div>
</template>

<style scoped>
.sst-tanstack {
  --sst-row-background: var(--cv-card-bg, #1a1a2e);
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

.sst-tanstack-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  margin-bottom: 6px;
}

.sst-tanstack-toolbar-label {
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.sst-tanstack-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sst-tanstack-status-info {
  font-size: 11px;
}

.sst-tanstack-scroll {
  position: relative;
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow-x: auto;
  overflow-y: scroll;
  scrollbar-gutter: stable;
  scrollbar-width: auto;
  scrollbar-color: rgba(127, 127, 127, 0.68) rgba(127, 127, 127, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.sst-tanstack-scroll::-webkit-scrollbar {
  width: 14px;
  height: 14px;
  background: rgba(127, 127, 127, 0.12);
}

.sst-tanstack-scroll::-webkit-scrollbar-track,
.sst-tanstack-scroll::-webkit-scrollbar-corner {
  background: rgba(127, 127, 127, 0.12);
}

.sst-tanstack-scroll::-webkit-scrollbar-thumb {
  min-height: 28px;
  background-color: rgba(127, 127, 127, 0.68);
  background-clip: content-box;
  border: 3px solid transparent;
  border-radius: 999px;
}

.sst-tanstack-scroll::-webkit-scrollbar-thumb:hover {
  background-color: rgba(127, 127, 127, 0.88);
}

.sst-tanstack-header {
  position: sticky;
  display: flex;
  top: 0;
  z-index: 30;
  height: 36px;
  background: var(--cv-card-bg, #1a1a2e);
  border-bottom: 1px solid rgba(255, 255, 255, 0.14);
}

.sst-tanstack-body {
  position: relative;
}

.sst-tanstack-row {
  position: absolute;
  display: flex;
  top: 0;
  left: 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.sst-tanstack-row:hover .sst-tanstack-cell {
  background-color: var(--sst-row-background);
  background-image: linear-gradient(rgba(127, 127, 127, 0.1), rgba(127, 127, 127, 0.1));
}

.sst-tanstack-row--placeholder {
  opacity: 0.45;
}

.sst-tanstack-cell {
  position: absolute;
  top: 0;
  height: 36px;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  overflow: hidden;
  padding: 0 8px;
  line-height: 35px;
  white-space: nowrap;
  text-overflow: ellipsis;
  background-color: var(--sst-row-background);
  border-right: 1px solid rgba(255, 255, 255, 0.08);
}

.sst-tanstack-cell--header {
  font-weight: 600;
}

.sst-tanstack-cell--pinned {
  position: sticky;
  z-index: 20;
  justify-content: center;
  background-color: var(--sst-row-background);
}

.sst-tanstack-cell--defect {
  z-index: 19;
  justify-content: flex-start;
  box-shadow: 2px 0 3px rgba(0, 0, 0, 0.18);
}

.sst-tanstack-header .sst-tanstack-cell--pinned {
  z-index: 40;
}

.sst-tanstack-column-header {
  display: flex;
  align-items: center;
  width: 100%;
  min-width: 0;
  gap: 4px;
}

.sst-tanstack-column-title {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sst-tanstack-column-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 1px;
}

.sst-tanstack-sort-button,
.sst-tanstack-filter-button {
  --n-width: 20px !important;
  --n-height: 20px !important;
  font-size: 12px;
}

.sst-tanstack-sort-button--active,
.sst-tanstack-filter-button--active {
  color: var(--cv-primary, #36ad6a);
}

.sst-tanstack-checkbox {
  width: 14px;
  height: 14px;
  margin: 0;
}

.sst-tanstack-empty {
  position: sticky;
  left: 0;
  display: flex;
  min-height: 120px;
  align-items: center;
  justify-content: center;
}

.sst-tanstack-error {
  padding-top: 4px;
  font-size: 12px;
}
</style>
