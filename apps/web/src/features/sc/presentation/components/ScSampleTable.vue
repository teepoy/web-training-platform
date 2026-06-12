<script setup lang="ts">
import { computed, h, ref, watch } from "vue";
import {
  NButton,
  NDataTable,
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
import type {
  ScSampleTableFilter,
  ScSampleTableSort,
} from "@/features/sc/domain/sampleTable";
import { getInspectionSampleTableRowsApiV1ScInspectionsInspectionTimeWaferKeySampleTableRowsPost } from "@/generated/orval/endpoints/api";
import type { ScSampleTableRow } from "@/generated/orval/models/scSampleTableRow";

const props = defineProps<{
  /** @deprecated Use defectIds plus inspection identity. */
  samples?: ScSampleItem[];
  defectIds?: string[];
  inspectionTime?: string;
  waferKey?: number;
  loading: boolean;
  total: number;
  selectedDefectIds?: ReadonlySet<number>;
  filter?: ScSampleTableFilter;
  sort?: ScSampleTableSort | null;
  reticleXDieCount?: number;
  reticleYDieCount?: number;
  reticleXDieShift?: number;
  reticleYDieShift?: number;
}>();

const emit = defineEmits<{
  (e: "selection-change", ids: number[]): void;
  (e: "filter-change", filter: ScSampleTableFilter): void;
  (
    e: "sort-change",
    sort: { field: string; direction: "asc" | "desc" | null },
  ): void;
}>();

interface ColumnDefinition {
  key: keyof ScSampleTableRow;
  title: string;
  width: number;
  filter: "set" | "range";
  render?: (row: ScSampleTableRow) => string;
}

const columnDefinitions: ColumnDefinition[] = [
  { key: "defect_id", title: "Defect ID", width: 100, filter: "set" },
  { key: "test_id", title: "Test ID", width: 80, filter: "set" },
  { key: "index_x", title: "Index X", width: 70, filter: "range" },
  { key: "index_y", title: "Index Y", width: 70, filter: "range" },
  { key: "wafer_x", title: "Wafer X", width: 90, filter: "range" },
  { key: "wafer_y", title: "Wafer Y", width: 90, filter: "range" },
  { key: "die_x", title: "Die X", width: 70, filter: "range" },
  { key: "die_y", title: "Die Y", width: 70, filter: "range" },
  { key: "size_x", title: "Size X", width: 70, filter: "range" },
  { key: "size_y", title: "Size Y", width: 70, filter: "range" },
  { key: "size_d", title: "Size D", width: 70, filter: "range" },
  { key: "area", title: "Area", width: 80, filter: "range" },
  { key: "class_number", title: "Class", width: 70, filter: "set" },
  { key: "rough_bin", title: "Rough Bin", width: 80, filter: "set" },
  { key: "final_bin", title: "Final Bin", width: 80, filter: "set" },
  { key: "manual_bin", title: "Manual Bin", width: 90, filter: "set" },
  { key: "adder", title: "Adder", width: 70, filter: "set" },
  { key: "cluster_id", title: "Cluster ID", width: 80, filter: "set" },
  {
    key: "kill_ratio",
    title: "Kill Ratio",
    width: 90,
    filter: "range",
    render: (row) => row.kill_ratio.toFixed(3),
  },
];

const PAGE_SIZE = 1000;
const SCROLL_LOAD_THRESHOLD_PX = 240;
const SCROLL_X = 1590;

const resolvedDefectIds = computed(
  () =>
    props.defectIds ??
    (props.samples ?? []).map((sample) => String(sample.defectId)),
);
const queryEnabled = computed(
  () => Boolean(props.inspectionTime) && props.waferKey !== undefined,
);
const tableQueryKey = computed(() =>
  [
    props.inspectionTime,
    props.waferKey,
    resolvedDefectIds.value.join(","),
    JSON.stringify(props.filter ?? {}),
    JSON.stringify(props.sort ?? null),
  ].join(":"),
);
const filterOptionsScopeKey = computed(() =>
  [
    props.inspectionTime,
    props.waferKey,
    resolvedDefectIds.value.join(","),
  ].join(":"),
);

const rows = ref<ScSampleTableRow[]>([]);
const serverTotal = ref(props.total);
const nextPage = ref(0);
const isFetching = ref(false);
const pageError = ref<string | null>(null);
const selectedIds = ref<Set<number>>(new Set());
const filterState = ref<
  Record<string, { min: number | null; max: number | null }>
>({});
const discoveredSetFilterValues = ref<Record<string, Array<string | number>>>(
  {},
);
let requestVersion = 0;

const hasMore = computed(() => rows.value.length < serverTotal.value);
const checkedRowKeys = computed<DataTableRowKey[]>(() =>
  Array.from(selectedIds.value),
);

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
  if (
    !state ||
    state.min === null ||
    state.max === null ||
    state.min > state.max
  ) {
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
  const definition = columnDefinitions.find(
    (column) => String(column.key) === field,
  );
  if (definition?.filter !== "set") return;

  const selected = filterState[field];
  const values = Array.isArray(selected)
    ? selected.filter(
        (value): value is string | number =>
          typeof value === "string" || typeof value === "number",
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

const columns = computed<DataTableColumns<ScSampleTableRow>>(() => [
  {
    type: "selection",
    fixed: "left",
    width: 40,
  },
  ...columnDefinitions.map(
    (definition): DataTableBaseColumn<ScSampleTableRow> => {
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
          definition.filter === "set"
            ? getSetFilterValues(field)
            : getRangeFilterValues(field),
        filterOptions:
          definition.filter === "set"
            ? getSetFilterOptions(definition)
            : undefined,
        filterMultiple: definition.filter === "set",
        renderFilterMenu:
          definition.filter === "range"
            ? ({ hide }: { hide: () => void }) =>
                renderRangeFilterMenu(field, hide)
            : undefined,
        render: definition.render
          ? (row: ScSampleTableRow) => definition.render?.(row) ?? ""
          : undefined,
      };
    },
  ),
]);

function updateSelection(keys: DataTableRowKey[]): void {
  const next = new Set(
    keys.map(Number).filter((value) => Number.isFinite(value)),
  );
  selectedIds.value = next;
  emit("selection-change", Array.from(next));
}

function toggleRow(row: ScSampleTableRow): void {
  const id = Number(row.defect_id);
  if (!Number.isFinite(id)) return;
  const next = new Set(selectedIds.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  selectedIds.value = next;
  emit("selection-change", Array.from(next));
}

function rowProps(row: ScSampleTableRow): Record<string, unknown> {
  return {
    class: selectedIds.value.has(Number(row.defect_id))
      ? "sst-row--selected"
      : undefined,
    onClick: (event: MouseEvent) => {
      const target = event.target;
      if (
        target instanceof Element &&
        target.closest(".n-checkbox, button, input")
      ) {
        return;
      }
      toggleRow(row);
    },
  };
}

async function fetchNextPage(): Promise<void> {
  if (!queryEnabled.value || isFetching.value || !hasMore.value) return;

  const page = nextPage.value;
  const version = requestVersion;
  isFetching.value = true;
  pageError.value = null;
  try {
    const { data } =
      await getInspectionSampleTableRowsApiV1ScInspectionsInspectionTimeWaferKeySampleTableRowsPost(
        props.inspectionTime!,
        props.waferKey!,
        {
          defect_ids: resolvedDefectIds.value,
          page,
          page_size: PAGE_SIZE,
          filter: props.filter,
          sort: props.sort ?? undefined,
          reticle_x_die_count: props.reticleXDieCount ?? 10,
          reticle_y_die_count: props.reticleYDieCount ?? 10,
          reticle_x_die_shift: props.reticleXDieShift ?? 0,
          reticle_y_die_shift: props.reticleYDieShift ?? 0,
        },
      );
    if (!data || !("items" in data)) {
      throw new Error("Invalid sample table response");
    }
    if (version !== requestVersion) return;

    rows.value = page === 0 ? data.items : [...rows.value, ...data.items];
    for (const definition of columnDefinitions) {
      if (definition.filter !== "set") continue;
      const field = String(definition.key);
      const values = new Map(
        (discoveredSetFilterValues.value[field] ?? []).map((value) => [
          String(value),
          value,
        ]),
      );
      for (const row of data.items) {
        const value = row[definition.key];
        if (typeof value === "string" || typeof value === "number") {
          values.set(String(value), value);
        }
      }
      discoveredSetFilterValues.value[field] = Array.from(values.values());
    }
    serverTotal.value = data.total;
    nextPage.value = page + 1;
  } catch (error) {
    if (version === requestVersion) {
      pageError.value =
        error instanceof Error
          ? error.message
          : "Failed to load sample table rows";
    }
  } finally {
    if (version === requestVersion) {
      isFetching.value = false;
    }
  }
}

function handleScroll(event: Event): void {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const remaining =
    target.scrollHeight - target.scrollTop - target.clientHeight;
  if (remaining <= SCROLL_LOAD_THRESHOLD_PX) {
    void fetchNextPage();
  }
}

function clearSelection(): void {
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
    nextPage.value = 0;
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
  getDefectCoords(defectId: number): {
    waferX: number;
    waferY: number;
    dieX: number;
    dieY: number;
    reticleX: number;
    reticleY: number;
  } | undefined {
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
      <NText depth="2" class="sst-header-label">
        Sample Data ({{ serverTotal }})
      </NText>
      <div class="sst-header-actions">
        <NButton
          v-if="selectedIds.size > 0"
          size="tiny"
          quaternary
          @click="clearSelection"
        >
          Clear Selection ({{ selectedIds.size }})
        </NButton>
        <NText v-if="serverTotal > 0" depth="3" class="sst-loaded-info">
          {{ rows.length }} / {{ serverTotal }} loaded
        </NText>
      </div>
    </div>

    <NDataTable
      class="sst-table"
      :columns="columns"
      :data="rows"
      :row-key="(row: ScSampleTableRow) => Number(row.defect_id)"
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
</style>
