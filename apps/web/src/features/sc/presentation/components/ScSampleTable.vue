<script setup lang="ts">
import { computed, h, ref, watch } from "vue";
import {
  NButton,
  NCheckbox,
  NDataTable,
  NInput,
  NInputNumber,
  NSpace,
  NText,
  type DataTableBaseColumn,
  type DataTableColumns,
  type DataTableFilterState,
  type DataTableRowKey,
  type DataTableSortState,
} from "naive-ui";
import type { ScSampleItem } from "@/features/sc/generated/proto/sc/v1/sample_pb";
import type { ScSampleTableFilter, ScSampleTableSort } from "@/features/sc/domain/sampleTable";
import type {
  ScSampleTableDataSource,
  ScSampleTableDisplayRow,
} from "@/features/sc/domain/workbenchInteraction";

const props = defineProps<{
  /** @deprecated Use defectIds plus inspection identity. */
  samples?: ScSampleItem[];
  dataSource?: ScSampleTableDataSource;
  defectIds?: string[];
  loading: boolean;
  total: number;
  selectedDefectIds?: ReadonlySet<number>;
  filter?: ScSampleTableFilter;
  sort?: ScSampleTableSort | null;
  reticleXDieCount?: number;
  reticleYDieCount?: number;
  reticleXDieShift?: number;
  reticleYDieShift?: number;
  showReclassifyColumns?: boolean;
  showGlobalFilterAction?: boolean;
  enableSelection?: boolean;
}>();

const emit = defineEmits<{
  (e: "selection-change", ids: number[]): void;
  (e: "apply-selection", ids: number[]): void;
  (e: "apply-filter-as-global", filter: ScSampleTableFilter): void;
  (e: "filter-change", filter: ScSampleTableFilter): void;
  (e: "sort-change", sort: { field: string; direction: "asc" | "desc" | null }): void;
}>();

interface ColumnDefinition {
  key: keyof ScSampleTableDisplayRow;
  title: string;
  width: number;
  filter: "set" | "range";
  render?: (row: ScSampleTableDisplayRow) => string;
}

const columnDefinitions: ColumnDefinition[] = [
  { key: "defect_id", title: "Defect ID", width: 130, filter: "set" },
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
];

const PAGE_SIZE = 1000;
const SELECT_ALL_LIMIT = 50_000;
const SCROLL_LOAD_THRESHOLD_PX = 240;
const SCROLL_X = computed(() => (props.showReclassifyColumns ? 1870 : 1590));
const activeColumnDefinitions = computed(() =>
  props.showReclassifyColumns
    ? [...columnDefinitions, ...reclassifyColumnDefinitions]
    : columnDefinitions,
);

const resolvedDefectIds = computed(
  () => props.defectIds ?? (props.samples ?? []).map((sample) => String(sample.defectId)),
);
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
const serverTotal = ref(props.total);
const nextAnchor = ref<string | null>("0");
const isFetching = ref(false);
const isSelectingAll = ref(false);
const pageError = ref<string | null>(null);
const streamStatus = ref("");
const selectedIds = ref<Set<number>>(new Set());
const filterState = ref<Record<string, { min: number | null; max: number | null }>>({});
const setFilterSearch = ref<Record<string, string>>({});
const discoveredSetFilterValues = ref<Record<string, Array<string | number>>>({});
let requestVersion = 0;

const hasMore = computed(() => nextAnchor.value !== null);
const checkedRowKeys = computed<DataTableRowKey[]>(() => Array.from(selectedIds.value));
const hasActiveFilter = computed(() => Object.keys(props.filter ?? {}).length > 0);
const selectionEnabled = computed(() => props.enableSelection === true);

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
      operator: "between",
      min: state.min,
      max: state.max,
    },
  });
}

function clearFilter(field: string): void {
  const next = { ...(props.filter ?? {}) };
  delete next[field];
  filterState.value[field] = { min: null, max: null };
  emit("filter-change", next);
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
  return filter?.operator === "in" ? filter.values : [];
}

function getRangeFilterValues(field: string): number[] {
  const filter = props.filter?.[field];
  return filter?.operator === "between" ? [filter.min, filter.max] : [];
}

function getSetFilterOptions(definition: ColumnDefinition) {
  const field = definition.key;
  const values = new Map<string, string | number>();
  for (const value of discoveredSetFilterValues.value[String(field)] ?? []) {
    values.set(String(value), value);
  }
  for (const value of getSetFilterValues(String(field))) {
    values.set(String(value), value);
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

function applySetFilter(field: string, values: Array<string | number>): void {
  const next = { ...(props.filter ?? {}) };
  if (values.length === 0) {
    delete next[field];
  } else {
    next[field] = { operator: "in", values };
  }
  emit("filter-change", next);
}

function renderSetFilterMenu(definition: ColumnDefinition, hide: () => void) {
  const field = String(definition.key);
  const search = (setFilterSearch.value[field] ?? "").trim().toLowerCase();
  const selected = new Set(getSetFilterValues(field).map(String));
  const options = getSetFilterOptions(definition).filter((option) =>
    search.length === 0 ? true : option.label.toLowerCase().includes(search),
  );

  return h("div", { class: "sst-filter-popover sst-filter-popover--set" }, [
    h(NInput, {
      value: setFilterSearch.value[field] ?? "",
      placeholder: "Search",
      size: "small",
      clearable: true,
      "onUpdate:value": (value: string) => {
        setFilterSearch.value[field] = value;
      },
    }),
    h(
      "div",
      { class: "sst-set-filter-options" },
      options.length > 0
        ? options.map((option) =>
            h(
              NCheckbox,
              {
                key: String(option.value),
                checked: selected.has(String(option.value)),
                "onUpdate:checked": (checked: boolean) => {
                  const current = getSetFilterValues(field);
                  const currentKeys = new Set(current.map(String));
                  const optionKey = String(option.value);
                  if (checked) currentKeys.add(optionKey);
                  else currentKeys.delete(optionKey);
                  const valuesByKey = new Map<string, string | number>();
                  for (const item of current) valuesByKey.set(String(item), item);
                  for (const item of getSetFilterOptions(definition)) {
                    valuesByKey.set(String(item.value), item.value);
                  }
                  applySetFilter(
                    field,
                    Array.from(currentKeys)
                      .map((key) => valuesByKey.get(key))
                      .filter(
                        (value): value is string | number =>
                          typeof value === "string" || typeof value === "number",
                      ),
                  );
                },
              },
              () => option.label,
            ),
          )
        : [h(NText, { depth: 3, class: "sst-set-filter-empty" }, () => "No matches")],
    ),
    h(NSpace, { size: 4 }, () => [
      h(
        NButton,
        {
          size: "tiny",
          quaternary: true,
          onClick: () => {
            setFilterSearch.value[field] = "";
          },
        },
        () => "Reset",
      ),
      h(
        NButton,
        {
          size: "tiny",
          quaternary: true,
          onClick: () => {
            applySetFilter(field, []);
            hide();
          },
        },
        () => "Clear",
      ),
      h(
        NButton,
        {
          size: "tiny",
          type: "primary",
          onClick: () => hide(),
        },
        () => "Done",
      ),
    ]),
  ]);
}

function renderRangeFilterMenu(field: string, hide: () => void) {
  return h("div", { class: "sst-filter-popover" }, [
    h(NSpace, { wrap: false }, () => [
      h(NInputNumber, {
        value: getFilterState(field).min,
        placeholder: "Min",
        size: "small",
        style: { width: "100px" },
        "onUpdate:value": (value: number | null) => {
          getFilterState(field).min = value;
        },
      }),
      h(NInputNumber, {
        value: getFilterState(field).max,
        placeholder: "Max",
        size: "small",
        style: { width: "100px" },
        "onUpdate:value": (value: number | null) => {
          getFilterState(field).max = value;
        },
      }),
    ]),
    h(NSpace, { size: 4 }, () => [
      h(
        NButton,
        {
          size: "tiny",
          onClick: () => {
            applyRangeFilter(field);
            hide();
          },
        },
        () => "Apply",
      ),
      h(
        NButton,
        {
          size: "tiny",
          quaternary: true,
          onClick: () => {
            clearFilter(field);
            hide();
          },
        },
        () => "Clear",
      ),
    ]),
  ]);
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
    next[field] = { operator: "in", values };
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
          definition.filter === "set"
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
        (discoveredSetFilterValues.value[field] ?? []).map((value) => [String(value), value]),
      );
      for (const row of response.items) {
        const value = row[definition.key];
        if (typeof value === "string" || typeof value === "number") {
          values.set(String(value), value);
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

async function selectAllMatching(): Promise<void> {
  if (!selectionEnabled.value) return;
  if (!queryEnabled.value || isSelectingAll.value) return;
  if (serverTotal.value > SELECT_ALL_LIMIT) {
    pageError.value = `Select All supports up to ${SELECT_ALL_LIMIT.toLocaleString()} rows. Narrow the selection by map location or filters first.`;
    return;
  }
  const hasFilter = props.filter && Object.keys(props.filter).length > 0;
  if (!hasFilter && resolvedDefectIds.value.length > 0) {
    if (resolvedDefectIds.value.length > SELECT_ALL_LIMIT) {
      pageError.value = `Select All supports up to ${SELECT_ALL_LIMIT.toLocaleString()} rows. Narrow the selection by map location or filters first.`;
      return;
    }
    const ids = resolvedDefectIds.value.map(Number).filter(Number.isFinite);
    selectedIds.value = new Set(ids);
    emit("selection-change", ids);
    return;
  }

  const version = requestVersion;
  isSelectingAll.value = true;
  pageError.value = null;
  try {
    const ids: number[] = [];
    let anchor: string | null = "0";
    while (anchor !== null) {
      const response = await props.dataSource!.loadRows({
        defectIds: resolvedDefectIds.value,
        anchor,
        limit: SELECT_ALL_LIMIT,
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
      ids.push(...response.items.map((row) => Number(row.defect_id)).filter(Number.isFinite));
      anchor = response.nextAnchor;
      if (version !== requestVersion) return;
      await new Promise((resolve) => window.setTimeout(resolve, 0));
    }
    selectedIds.value = new Set(ids);
    emit("selection-change", ids);
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : "Failed to select all rows";
  } finally {
    if (version === requestVersion) isSelectingAll.value = false;
  }
}

function applySelectionAsDefects(): void {
  if (!selectionEnabled.value) return;
  emit("apply-selection", Array.from(selectedIds.value));
}

function applyFilterAsGlobal(): void {
  emit("apply-filter-as-global", { ...(props.filter ?? {}) });
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
  },
  { immediate: true },
);

watch(
  tableQueryKey,
  () => {
    requestVersion += 1;
    rows.value = [];
    serverTotal.value = resolvedDefectIds.value.length || props.total;
    nextAnchor.value = "0";
    isFetching.value = false;
    pageError.value = null;
    if (queryEnabled.value) void fetchNextPage();
  },
  { immediate: true },
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
        value?.operator === "between"
          ? { min: value.min, max: value.max }
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
</script>

<template>
  <div class="sst">
    <div class="sst-header">
      <NText depth="2" class="sst-header-label"> Sample Data ({{ serverTotal }}) </NText>
      <div class="sst-header-actions">
        <NButton
          v-if="selectionEnabled && serverTotal > 0"
          size="tiny"
          quaternary
          :loading="isSelectingAll"
          @click="selectAllMatching"
        >
          Select All ({{ serverTotal }})
        </NButton>
        <NButton
          v-if="selectionEnabled && selectedIds.size > 0"
          size="tiny"
          quaternary
          @click="clearSelection"
        >
          Clear Selection ({{ selectedIds.size }})
        </NButton>
        <NButton
          v-if="showGlobalFilterAction && hasActiveFilter"
          size="tiny"
          quaternary
          type="primary"
          @click="applyFilterAsGlobal"
        >
          Set Filter as Global
        </NButton>
        <NButton
          v-if="selectionEnabled && selectedIds.size > 0"
          size="tiny"
          quaternary
          type="primary"
          @click="applySelectionAsDefects"
        >
          Set as Selected Defects
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

.sst-filter-popover {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
}

.sst-filter-popover--set {
  width: 220px;
}

.sst-set-filter-options {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 220px;
  overflow-y: auto;
}

.sst-set-filter-empty {
  font-size: 12px;
  padding: 4px 0;
}
</style>
