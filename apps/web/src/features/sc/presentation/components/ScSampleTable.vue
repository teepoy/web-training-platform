<script setup lang="ts">
import { computed, h, onUpdated, ref, watch } from "vue";
import {
  NButton,
  NDataTable,
  NText,
  type DataTableBaseColumn,
  type DataTableColumns,
  type DataTableFilterState,
  type DataTableRowKey,
  type DataTableSortState,
} from "naive-ui";
import type { ScSampleTableFilter, ScSampleTableSort } from "@/features/sc/domain/sampleTable";
import type { ScSampleTableDisplayRow } from "@/features/sc/domain/workbenchInteraction";
import type { ScSampleTableEmits, ScSampleTableProps } from "./scSampleTableContract";
import ScRangeFilterMenu from "./ScRangeFilterMenu.vue";
import ScSetFilterMenu from "./ScSetFilterMenu.vue";
import ScTextFilterMenu from "./ScTextFilterMenu.vue";

const props = defineProps<ScSampleTableProps>();

const emit = defineEmits<ScSampleTableEmits>();

interface ColumnDefinition {
  key: keyof ScSampleTableDisplayRow;
  title: string;
  width: number;
  filter: "set" | "range";
  render?: (row: ScSampleTableDisplayRow) => string;
}

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
const SCROLL_LOAD_THRESHOLD_PX = 240;
const SCROLL_X = computed(() => (props.showReclassifyColumns ? 2110 : 1700));
const activeColumnDefinitions = computed(() =>
  props.showReclassifyColumns
    ? [...columnDefinitions, ...reclassifyColumnDefinitions]
    : columnDefinitions,
);

const resolvedDefectIds = computed(() => props.defectIds ?? []);
const queryEnabled = computed(() => Boolean(props.dataSource));
const tableQueryKey = computed(() =>
  [
    props.dataSource?.scopeKey ?? "",
    resolvedDefectIds.value.join(","),
    JSON.stringify(props.filter ?? {}),
    JSON.stringify(props.sort ?? null),
  ].join(":"),
);
const filterOptionsScopeKey = computed(() =>
  [props.dataSource?.scopeKey ?? "", resolvedDefectIds.value.join(",")].join(":"),
);

const rows = ref<ScSampleTableDisplayRow[]>([]);
const serverTotal = ref(props.total ?? 0);
const nextAnchor = ref<string | null>("0");
const isFetching = ref(false);
const pageError = ref<string | null>(null);
const streamStatus = ref("");
const selectedIds = ref<Set<number>>(new Set());
const filterState = ref<Record<string, { min: number | null; max: number | null }>>({});
const setFilterSearch = ref<Record<string, string>>({});
const setFilterDraft = ref<Record<string, Set<string>>>({});
const discoveredSetFilterValues = ref<Record<string, Array<string | number>>>({});
const searchedSetFilterValues = ref<Record<string, Array<string | number>>>({});
const setFilterSearchLoading = ref<Record<string, boolean>>({});
let requestVersion = 0;

const hasMore = computed(() => nextAnchor.value !== null);
const checkedRowKeys = computed<DataTableRowKey[]>(() => Array.from(selectedIds.value));
const hasAnyFilter = computed(() => Object.keys(props.filter ?? {}).length > 0);
const selectionEnabled = computed(() => props.enableSelection === true);

function normalizeFilterValue(field: string, value: string | number): string | number {
  if (field !== "defect_id") return value;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : value;
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

function applyRangeFilter(field: string): void {
  const state = filterState.value[field];
  if (!state || state.min === null || state.max === null || state.min > state.max) {
    return;
  }
  emit("filter-change", {
    ...(props.filter ?? {}),
    [field]: {
      filterType: "number",
      type: "inRange",
      filter: state.min,
      filterTo: state.max,
    },
  });
}

function clearFilter(field: string): void {
  const next = { ...(props.filter ?? {}) };
  delete next[field];
  filterState.value[field] = { min: null, max: null };
  emit("filter-change", next);
}

function clearAllFilters(): void {
  setFilterSearch.value = {};
  setFilterDraft.value = {};
  filterState.value = {};
  emit("filter-change", {});
}

function handleSorter(sortState: DataTableSortState | null): void {
  if (!sortState || sortState.order === false) {
    emit("sort-change", {
      field: String(sortState?.columnKey ?? props.sort?.field ?? ""),
      direction: null,
    });
    return;
  }
  emit("sort-change", {
    field: String(sortState.columnKey),
    direction: sortState.order === "ascend" ? "asc" : "desc",
  });
}

function getSetFilterValues(field: string): Array<string | number> {
  const filter = props.filter?.[field];
  return filter?.filterType === "set"
    ? filter.values.map((value) => normalizeFilterValue(field, value))
    : [];
}

function getRangeFilterValues(field: string): number[] {
  const filter = props.filter?.[field];
  return filter?.filterType === "number" && filter.type === "inRange"
    ? [filter.filter, filter.filterTo]
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

function filterWithoutField(field: string): ScSampleTableFilter | undefined {
  const source = props.filter ?? {};
  const next = { ...source };
  delete next[field];
  return Object.keys(next).length > 0 ? next : undefined;
}

async function searchSetFilterOptions(field: string): Promise<void> {
  const search = setFilterSearch.value[field] ?? "";
  if (!props.dataSource?.loadDistinctValues) return;

  setFilterSearchLoading.value = { ...setFilterSearchLoading.value, [field]: true };
  try {
    const values = await props.dataSource.loadDistinctValues({
      field,
      search,
      limit: 200,
      filter: filterWithoutField(field),
      sort: props.sort,
    });
    searchedSetFilterValues.value = {
      ...searchedSetFilterValues.value,
      [field]: values,
    };
  } finally {
    setFilterSearchLoading.value = { ...setFilterSearchLoading.value, [field]: false };
  }
}

function applySetFilter(field: string, values: Array<string | number>): void {
  const next = { ...(props.filter ?? {}) };
  if (values.length === 0) {
    delete next[field];
  } else {
    next[field] = {
      filterType: "set",
      values: values.map((value) => normalizeFilterValue(field, value)),
    };
  }
  emit("filter-change", next);
}

function renderSetFilterMenu(definition: ColumnDefinition, hide: () => void) {
  const field = String(definition.key);
  const appliedValues = new Set(getSetFilterValues(field).map(String));

  if (!setFilterDraft.value[field]) {
    setFilterDraft.value[field] = new Set(appliedValues);
  }
  const allOptions = getSetFilterOptions(definition);
  return h(ScSetFilterMenu, {
    search: setFilterSearch.value[field] ?? "",
    appliedValues: Array.from(appliedValues),
    draftValues: Array.from(setFilterDraft.value[field] ?? []),
    options: allOptions,
    "onUpdate:search": (value: string) => {
      setFilterSearch.value[field] = value;
    },
    "onUpdate:draftValues": (values: string[]) => {
      setFilterDraft.value[field] = new Set(values);
    },
    onSearchOptions: () => {
      void searchSetFilterOptions(field);
    },
    onApply: (values: Array<string | number>) => applySetFilter(field, values),
    onClose: hide,
  });
}

function renderRangeFilterMenu(field: string, hide: () => void) {
  const state = getFilterState(field);
  return h(ScRangeFilterMenu, {
    min: state.min,
    max: state.max,
    "onUpdate:min": (value: number | null) => {
      state.min = value;
    },
    "onUpdate:max": (value: number | null) => {
      state.max = value;
    },
    onApply: () => applyRangeFilter(field),
    onClear: () => clearFilter(field),
    onClose: hide,
  });
}

function renderTextFilterMenu(hide: () => void) {
  return h(ScTextFilterMenu, {
    appliedValues: getSetFilterValues("defect_id"),
    onApply: (values: Array<string | number>) => applySetFilter("defect_id", values),
    onClose: hide,
  });
}

function handleFilters(
  filterState: DataTableFilterState,
  sourceColumn: { key: string | number },
): void {
  const field = String(sourceColumn.key);
  const definition = activeColumnDefinitions.value.find((column) => String(column.key) === field);
  if (definition?.filter !== "set") return;

  const selected = filterState[field];
  const values = Array.isArray(selected)
    ? selected.filter(
        (value): value is string | number => typeof value === "string" || typeof value === "number",
      )
    : [];
  const next = { ...(props.filter ?? {}) };
  if (values.length === 0) {
    delete next[field];
  } else {
    next[field] = {
      filterType: "set",
      values: values.map((value) => normalizeFilterValue(field, value)),
    };
  }
  emit("filter-change", next);
}

const columns = computed<DataTableColumns<ScSampleTableDisplayRow>>(() => [
  ...(selectionEnabled.value
    ? [
        {
          type: "selection" as const,
          fixed: "left" as const,
          width: 40,
        },
      ]
    : []),
  ...activeColumnDefinitions.value.map(
    (definition): DataTableBaseColumn<ScSampleTableDisplayRow> => {
      const field = String(definition.key);
      return {
        key: definition.key,
        title: definition.title,
        width: definition.width,
        fixed: definition.key === "defect_id" ? ("left" as const) : undefined,
        ellipsis: { tooltip: true },
        sorter: true,
        sortOrder:
          props.sort?.field === field
            ? props.sort.direction === "asc"
              ? ("ascend" as const)
              : ("descend" as const)
            : false,
        filter: true,
        filterOptionValues:
          definition.filter === "set" ? getSetFilterValues(field) : getRangeFilterValues(field),
        filterOptions: definition.filter === "set" ? getSetFilterOptions(definition) : undefined,
        filterMultiple: definition.filter === "set",
        renderFilterMenu:
          field === "defect_id"
            ? ({ hide }: { hide: () => void }) => renderTextFilterMenu(hide)
            : definition.filter === "set"
              ? ({ hide }: { hide: () => void }) => renderSetFilterMenu(definition, hide)
              : definition.filter === "range"
                ? ({ hide }: { hide: () => void }) => renderRangeFilterMenu(field, hide)
                : undefined,
        render: definition.render
          ? (row: ScSampleTableDisplayRow) => definition.render?.(row) ?? ""
          : undefined,
      };
    },
  ),
]);

function updateSelection(keys: DataTableRowKey[]): void {
  if (!selectionEnabled.value) return;
  const next = new Set(keys.map(Number).filter((value) => Number.isFinite(value)));
  selectedIds.value = next;
  emit("selection-change", Array.from(next));
}

function toggleRow(row: ScSampleTableDisplayRow): void {
  if (!selectionEnabled.value) return;
  const id = Number(row.defect_id);
  if (!Number.isFinite(id)) return;
  const next = new Set(selectedIds.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  selectedIds.value = next;
  emit("selection-change", Array.from(next));
}

function rowProps(row: ScSampleTableDisplayRow): Record<string, unknown> {
  if (!selectionEnabled.value) return {};
  return {
    class: selectedIds.value.has(Number(row.defect_id)) ? "sst-row--selected" : undefined,
    onClick: (event: MouseEvent) => {
      const target = event.target;
      if (target instanceof Element && target.closest(".n-checkbox, button, input")) {
        return;
      }
      toggleRow(row);
    },
  };
}

async function fetchNextPage(): Promise<void> {
  if (!queryEnabled.value || isFetching.value || !hasMore.value) return;

  const anchor = nextAnchor.value;
  if (anchor === null) return;
  const version = requestVersion;
  isFetching.value = true;
  pageError.value = null;
  try {
    streamStatus.value = "Loading sample rows...";
    const response = await props.dataSource!.loadRows({
      defectIds: resolvedDefectIds.value,
      anchor,
      limit: PAGE_SIZE,
      filter: props.filter,
      sort: props.sort,
      reticleOptions:
        props.reticleXDieCount !== undefined &&
        props.reticleYDieCount !== undefined &&
        props.reticleXDieShift !== undefined &&
        props.reticleYDieShift !== undefined
          ? {
              xDieCount: props.reticleXDieCount,
              yDieCount: props.reticleYDieCount,
              xDieShift: props.reticleXDieShift,
              yDieShift: props.reticleYDieShift,
            }
          : undefined,
    });
    if (version !== requestVersion) return;
    rows.value = anchor === "0" ? response.items : [...rows.value, ...response.items];
    for (const definition of activeColumnDefinitions.value) {
      if (definition.filter !== "set") continue;
      const field = String(definition.key);
      const values = new Map(
        (discoveredSetFilterValues.value[field] ?? []).map((value) => {
          const normalized = normalizeFilterValue(field, value);
          return [String(normalized), normalized];
        }),
      );
      for (const row of response.items) {
        const value = row[definition.key];
        if (typeof value === "string" || typeof value === "number") {
          const normalized = normalizeFilterValue(field, value);
          values.set(String(normalized), normalized);
        }
      }
      discoveredSetFilterValues.value[field] = Array.from(values.values());
    }
    serverTotal.value = response.total;
    nextAnchor.value = response.nextAnchor;
  } catch (error) {
    if (version === requestVersion) {
      pageError.value = error instanceof Error ? error.message : "Failed to load sample table rows";
    }
  } finally {
    if (version === requestVersion) {
      isFetching.value = false;
      streamStatus.value = "";
    }
  }
}

function handleScroll(event: Event): void {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const remaining = target.scrollHeight - target.scrollTop - target.clientHeight;
  if (remaining <= SCROLL_LOAD_THRESHOLD_PX) {
    void fetchNextPage();
  }
}

function clearSelection(): void {
  if (!selectionEnabled.value) return;
  selectedIds.value = new Set();
  emit("selection-change", []);
}

watch(
  filterOptionsScopeKey,
  () => {
    discoveredSetFilterValues.value = {};
    searchedSetFilterValues.value = {};
  },
  { immediate: true },
);

watch(
  tableQueryKey,
  () => {
    requestVersion += 1;
    rows.value = [];
    serverTotal.value = resolvedDefectIds.value.length || props.total || 0;
    nextAnchor.value = "0";
    isFetching.value = false;
    pageError.value = null;
    if (queryEnabled.value) void fetchNextPage();
  },
  { immediate: true },
);

watch(
  () => props.dataSource,
  () => {
    if (!props.dataSource || !queryEnabled.value) return;
    requestVersion += 1;
    rows.value = [];
    serverTotal.value = resolvedDefectIds.value.length || props.total || 0;
    nextAnchor.value = "0";
    isFetching.value = false;
    pageError.value = null;
    streamStatus.value = "";
    discoveredSetFilterValues.value = {};
    searchedSetFilterValues.value = {};
    void fetchNextPage();
  },
);

watch(
  () => props.selectedDefectIds,
  (ids) => {
    selectedIds.value = new Set(ids ?? []);
  },
  { immediate: true },
);

watch(
  () => props.filter,
  (filter) => {
    for (const definition of columnDefinitions) {
      const field = String(definition.key);
      const value = filter?.[field];
      filterState.value[field] =
        value?.filterType === "number" && value.type === "inRange"
          ? { min: value.filter, max: value.filterTo }
          : { min: null, max: null };
    }
  },
  { immediate: true, deep: true },
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
    const row = rows.value.find((r) => Number(r.defect_id) === defectId);
    if (!row) return undefined;
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

onUpdated(() => console.debug("[render] ScSampleTable"));
</script>

<template>
  <div class="sst">
    <div class="sst-header">
      <NText depth="2" class="sst-header-label"> Sample Data ({{ serverTotal }}) </NText>
      <div class="sst-header-actions">
        <NButton
          v-if="selectionEnabled && selectedIds.size > 0"
          size="tiny"
          quaternary
          @click="clearSelection"
        >
          Clear Selection ({{ selectedIds.size }})
        </NButton>
        <NButton v-if="hasAnyFilter" size="tiny" quaternary @click="clearAllFilters">
          Clear All Filters
        </NButton>
        <NText v-if="serverTotal > 0" depth="3" class="sst-loaded-info">
          {{ rows.length }} / {{ serverTotal }} loaded
        </NText>
        <NText v-if="streamStatus" depth="3" class="sst-loaded-info">
          {{ streamStatus }}
        </NText>
      </div>
    </div>

    <NDataTable
      class="sst-table"
      :columns="columns"
      :data="rows"
      :row-key="(row: ScSampleTableDisplayRow) => Number(row.defect_id)"
      :row-props="rowProps"
      :checked-row-keys="checkedRowKeys"
      :loading="loading || (isFetching && rows.length === 0)"
      :scroll-x="SCROLL_X"
      :min-row-height="36"
      :single-line="false"
      :striped="true"
      :virtual-scroll="true"
      :virtual-scroll-x="true"
      remote
      flex-height
      size="small"
      @scroll="handleScroll"
      @update:filters="handleFilters"
      @update:sorter="handleSorter"
      @update:checked-row-keys="updateSelection"
    >
      <template #empty>
        <NText depth="3">No samples</NText>
      </template>
    </NDataTable>

    <div v-if="isFetching && rows.length > 0" class="sst-footer">
      <NText depth="3">Loading more rows...</NText>
    </div>
    <NText v-if="pageError" type="error" class="sst-error">
      {{ pageError }}
    </NText>
  </div>
</template>

<style scoped>
.sst {
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

.sst-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  flex-shrink: 0;
}

.sst-header-label {
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.sst-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sst-loaded-info,
.sst-footer {
  font-size: 11px;
}

.sst-table {
  flex: 1;
  min-height: 0;
}

.sst-footer {
  padding-top: 4px;
  text-align: center;
}

.sst-error {
  padding-top: 4px;
  font-size: 12px;
}

:deep(.sst-row--selected td) {
  background: rgba(76, 128, 240, 0.15) !important;
}
</style>
