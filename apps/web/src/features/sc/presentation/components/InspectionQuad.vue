<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from "vue";
import { NButton, NSelect } from "naive-ui";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsOption } from "echarts";
import type { ECElementEvent } from "echarts/core";
import type { ScMapLassoSelection, ScMapSelectionCommand } from "@platform/sc-map-element";
import ScMapPanelBinned from "@/features/sc/presentation/components/ScMapPanelBinned.vue";
import ScGlobalFilterModal from "@/features/sc/presentation/components/ScGlobalFilterModal.vue";
import ScSampleTable from "@/features/sc/presentation/components/ScSampleTable.vue";
import ScBlinkVirtualTable from "@/features/sc/presentation/components/ScBlinkVirtualTable.vue";
import type { ScSampleTableFilter, ScSampleTableSort } from "@/features/sc/domain/sampleTable";
import {
  cloneScGlobalFilter,
  emptyScGlobalFilter,
  scGlobalFilterConditionCount,
  type ScGlobalFilter,
} from "@/features/sc/domain/globalFilter";
import type {
  ScSamplingGroupPopulation,
  ScSamplingProgram,
} from "@/features/sc/domain/samplingRules";
import type {
  ScDataColumn,
  ScTableSelectionConstraint,
} from "@/features/sc/domain/workbenchDataSource";
import type {
  ScLegendSource,
  ScMapRegion,
  ScMapSelectionMode,
  ScSelectionAction,
} from "@/features/sc/domain/workbenchInteraction";
import {
  DEFAULT_RETICLE_MAP_OPTIONS,
  normalizeReticleMapOptions,
  type ReticleMapOptions,
} from "@/features/sc/application/reticleMapOptions";
import { applyMapSelectionToGlobalFilter } from "@/features/sc/application/inspectionFilterPolicy";
import { useInspectionQuadData } from "@/features/sc/presentation/composables/useInspectionQuadData";
import type { ScSamplingCandidateOptions } from "@/features/sc/presentation/composables/useSqlInspectionModel";

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

const props = defineProps<{
  variant?: "preview" | "reclassify";
  datasetId?: string;
  collectionId?: string;
  collectionRevisionId?: string;
  inspectionTime: string;
  waferKey: number;
  annotationDrafts?: Record<string, string>;
  waferGeometry?: {
    waferRadiusNm: number;
    centerX: number;
    centerY: number;
    originX: number;
    originY: number;
    dieSizeX: number;
    dieSizeY: number;
  } | null;
  selectedDefectIds?: Array<number | string>;
  galleryRandomSamplingDefectIds?: Set<string>;
  globalFilter?: ScGlobalFilter;
  globalFilterTriggerTarget?: string | HTMLElement;
}>();

const emit = defineEmits<{
  (e: "clear-gallery-random-sampling"): void;
  (e: "selection-change", action: ScSelectionAction): void;
  (e: "update:globalFilter", filter: ScGlobalFilter): void;
}>();

const DEFAULT_COLUMN_PCT = 35;
const RECLASSIFY_ANNOTATION_PCT = 15;
const DEFAULT_MAP_PCT = 55;
const DEFAULT_BAR_PCT = 60;
const DEFAULT_RETICLE_DIE_SIZE = 100_000;
type MapMode = "wafer" | "die" | "reticle";
type MapViewport = { x: number; y: number; w: number; h: number };
const quadEl = ref<HTMLElement | null>(null);
const mapPanel = ref<InstanceType<typeof ScMapPanelBinned> | null>(null);
const leftPanelEl = ref<HTMLElement | null>(null);
const rightPanelEl = ref<HTMLElement | null>(null);
const columnPct = ref(DEFAULT_COLUMN_PCT);
const mapPct = ref(DEFAULT_MAP_PCT);
const barPct = ref(DEFAULT_BAR_PCT);
const HIGHLIGHT_MAX_DEFECTS = 9999;
const isColumnResizing = ref(false);
const isRowResizing = ref(false);
const isBarResizing = ref(false);
const globalDistinctValues = ref<Record<string, Array<string | number>>>({});
const globalNumericRanges = ref<Record<string, { min: number; max: number } | null>>({});
const globalNumericRangeLoading = ref<Record<string, boolean>>({});
const globalNumericRangeErrors = ref<Record<string, boolean>>({});
const globalFilterSearchVersions = new Map<string, number>();
const globalRangeVersions = new Map<string, number>();
// Preview uses the local fallback. ReclassifyPage supplies the controlled model
// so workflow consumers and outer route shells share the same Global Filter.
const localGlobalFilter = ref<ScGlobalFilter>(emptyScGlobalFilter());
const globalFilterModalVisible = ref(false);
const activeMapTab = ref<MapMode>("wafer");
const mapZoomByMode = ref<Record<MapMode, MapViewport | null>>(emptyMapZoomByMode());
const zoom = computed(() => mapZoomByMode.value[activeMapTab.value]);
const reticleOptions = ref<ReticleMapOptions>(
  normalizeReticleMapOptions(DEFAULT_RETICLE_MAP_OPTIONS),
);
const legendGroupBy = ref<ScLegendSource | null>(null);
function emptyHiddenLegendKeysBySource(): Record<ScLegendSource, string[]> {
  return { class: [], bin: [], annotation: [], prediction: [], final_class: [] };
}
const hiddenLegendKeysBySource = ref<Record<ScLegendSource, string[]>>(
  emptyHiddenLegendKeysBySource(),
);
const activeLegendSource = computed<ScLegendSource>(() => legendGroupBy.value ?? "class");
const activeHiddenLegendKeys = computed(
  () => hiddenLegendKeysBySource.value[activeLegendSource.value] ?? [],
);
const tableFilter = ref<ScSampleTableFilter>({});
const tableSort = ref<ScSampleTableSort | null>(null);
const localSelectedDefectIds = ref<string[]>([]);
type QueuedAreaSelection =
  | {
      kind: "box";
      mode: "wafer" | "die" | "reticle";
      region: ScMapRegion;
    }
  | {
      kind: "lasso";
      mode: "wafer" | "die" | "reticle";
      selection: ScMapLassoSelection;
      region: ScMapRegion;
    };

const isReclassify = computed(() => props.variant === "reclassify");
const globalFilterModel = computed<ScGlobalFilter>({
  get: () => props.globalFilter ?? localGlobalFilter.value,
  set: (filter) => {
    const snapshot = cloneScGlobalFilter(filter);
    if (props.globalFilter === undefined) {
      localGlobalFilter.value = snapshot;
      return;
    }
    emit("update:globalFilter", snapshot);
  },
});
const globalFilterCount = computed(() => scGlobalFilterConditionCount(globalFilterModel.value));
const tableFilterCount = computed(() => Object.keys(tableFilter.value).length);
const samplingCohortCount = computed(() => props.galleryRandomSamplingDefectIds?.size ?? 0);
const enabledLegendSources = computed<ScLegendSource[]>(() =>
  isReclassify.value
    ? ["class", "bin", "annotation", "prediction", "final_class"]
    : ["class", "bin"],
);
const mapColorMapScopeKey = computed(() =>
  props.collectionId && props.collectionRevisionId
    ? `collection:${props.collectionId}/${props.collectionRevisionId}`
    : props.datasetId
      ? `dataset:${props.datasetId}`
      : `inspection:${props.inspectionTime}:${props.waferKey}`,
);
const waferGeometryModel = computed(() => {
  const geometry = props.waferGeometry;
  if (!geometry) return null;
  return {
    ...geometry,
    dieSizeX: normalizeDieSize(geometry.dieSizeX),
    dieSizeY: normalizeDieSize(geometry.dieSizeY),
  };
});
const reticleDieSizeX = computed(() => normalizeDieSize(waferGeometryModel.value?.dieSizeX));
const reticleDieSizeY = computed(() => normalizeDieSize(waferGeometryModel.value?.dieSizeY));
const reticleProjectionModel = computed(() => ({
  options: reticleOptions.value,
  dieSizeX: reticleDieSizeX.value,
  dieSizeY: reticleDieSizeY.value,
}));

const { workbench, dataReady, model, reportDataError } = useInspectionQuadData({
  variant: computed(() => props.variant),
  datasetId: computed(() => props.datasetId),
  collectionId: computed(() => props.collectionId),
  collectionRevisionId: computed(() => props.collectionRevisionId),
  inspectionTime: computed(() => props.inspectionTime),
  waferKey: computed(() => props.waferKey),
  legendGroupBy: computed(() => legendGroupBy.value),
  globalFilter: globalFilterModel,
  tableFilter: computed(() => tableFilter.value),
  tableSort: computed(() => tableSort.value),
  reticle: reticleProjectionModel,
  galleryRandomSamplingDefectIds: computed(() => props.galleryRandomSamplingDefectIds),
});
const sampleTableColumns = ref<ScDataColumn[]>([]);
let sampleTableColumnsVersion = 0;

watch(
  () => model.sampleTableDataSource.value,
  async (source) => {
    const version = ++sampleTableColumnsVersion;
    sampleTableColumns.value = [];
    if (!source?.loadColumns) return;
    try {
      const columns = await source.loadColumns();
      if (version === sampleTableColumnsVersion) sampleTableColumns.value = columns;
    } catch (error) {
      if (version === sampleTableColumnsVersion) {
        reportDataError("Load sample-table descriptor failed", error);
      }
    }
  },
  { immediate: true },
);

async function querySamplingCandidateCount(options: ScSamplingCandidateOptions): Promise<number> {
  return model.querySamplingCandidateCount(options);
}

async function querySamplingDefectIds(
  program: ScSamplingProgram,
  seed: number,
  options: ScSamplingCandidateOptions,
): Promise<number[]> {
  return model.querySamplingDefectIds(program, seed, options);
}

async function querySamplingGroups(
  field: string,
  options: ScSamplingCandidateOptions,
): Promise<ScSamplingGroupPopulation[]> {
  return model.querySamplingGroups(field, options);
}

function openGlobalFilterModal(): void {
  globalFilterModalVisible.value = true;
}

function getSamplingContext(): {
  mapSelectionCount: number;
  tableSelectionAvailable: boolean;
} {
  const tableSelection = model.tableSelection.value;
  return {
    mapSelectionCount: model.mapSelectedDefectIds.value.length,
    tableSelectionAvailable:
      tableSelection.kind === "all" ||
      (tableSelection.kind === "ids" && tableSelection.ids.length > 0),
  };
}

function emptyMapZoomByMode(): Record<MapMode, MapViewport | null> {
  return { wafer: null, die: null, reticle: null };
}

function normalizeDieSize(value: number | null | undefined): number {
  return typeof value === "number" && Number.isFinite(value) && value > 0
    ? value
    : DEFAULT_RETICLE_DIE_SIZE;
}

function cloneSampleTableFilter(filter: ScSampleTableFilter): ScSampleTableFilter {
  return Object.fromEntries(
    Object.entries(filter).map(([field, condition]) => [
      field,
      condition.filterType === "set"
        ? { ...condition, values: [...condition.values] }
        : { ...condition },
    ]),
  );
}

function getGlobalFilter(): ScGlobalFilter {
  return cloneScGlobalFilter(globalFilterModel.value);
}

function clearGalleryRandomSamplingIfActive(): void {
  if (props.galleryRandomSamplingDefectIds?.size) emit("clear-gallery-random-sampling");
}

function handleGlobalFilterApply(filter: ScGlobalFilter): void {
  globalFilterModel.value = filter;
}

function handleActiveMapTabChange(mode: MapMode): void {
  activeMapTab.value = mode;
}

function handleMapZoomChange(viewport: MapViewport | null): void {
  mapZoomByMode.value = { ...mapZoomByMode.value, [activeMapTab.value]: viewport };
}

function handleReticleOptionsChange(options: ReticleMapOptions): void {
  reticleOptions.value = normalizeReticleMapOptions(options);
}

function handleLegendGroupByChange(source: ScLegendSource | null): void {
  legendGroupBy.value = source;
}

function normalizeHiddenLegendKeys(keys: readonly string[]): string[] {
  return [...new Set(keys)].sort();
}

function handleLegendHiddenChange(payload: { source: ScLegendSource; hiddenKeys: string[] }): void {
  const previousHiddenKeys = normalizeHiddenLegendKeys(
    hiddenLegendKeysBySource.value[payload.source] ?? [],
  );
  const nextHiddenKeys = normalizeHiddenLegendKeys(payload.hiddenKeys);
  if (
    previousHiddenKeys.length === nextHiddenKeys.length &&
    previousHiddenKeys.every((key, index) => key === nextHiddenKeys[index])
  ) {
    return;
  }
  hiddenLegendKeysBySource.value = {
    ...hiddenLegendKeysBySource.value,
    [payload.source]: nextHiddenKeys,
  };
  if (payload.source === activeLegendSource.value) {
    mapSelectionQueue.prune(nextHiddenKeys);
  }
}

async function commitMapSelectionFilter(mode: ScMapSelectionMode): Promise<void> {
  try {
    if (!(await mapSelectionQueue.prepareContextAction())) return;
    const next = applyMapSelectionToGlobalFilter(
      globalFilterModel.value,
      model.mapSelectedDefectIds.value,
      mode,
    );
    globalFilterModel.value = next;
    mapSelectionQueue.clear();
    selectedBarChartKey.value = null;
    mapSelectionResetVersion.value += 1;
  } catch (error) {
    reportDataError("Apply map selection to Global Filter failed", error);
  }
}

function handleInvertMapSelectionMode(): void {
  mapSelectionQueue.invert();
}

async function handleCopySelectedDefectIds(): Promise<void> {
  try {
    if (!(await mapSelectionQueue.prepareContextAction())) return;
    if (!navigator.clipboard) throw new Error("Clipboard API is unavailable");
    const ids = model.mapSelectedDefectIds.value;
    if (ids.length === 0) throw new Error("Current map selection is empty");
    await navigator.clipboard.writeText(ids.join("\n"));
  } catch (error) {
    reportDataError("Copy selected defect IDs failed", error);
  }
}

function handleTableFilterChange(filter: ScSampleTableFilter): void {
  tableFilter.value = cloneSampleTableFilter(filter);
}

function clearTableFilters(): void {
  tableFilter.value = {};
}

function handleReviewModeChange(mode: "patch" | "review"): void {
  const nextReviewMode = mode === "review";
  model.setReviewMode(nextReviewMode);
}

defineExpose({
  getGlobalFilter,
  getSamplingContext,
  querySamplingCandidateCount,
  querySamplingDefectIds,
  querySamplingGroups,
  filterDistinctValues: globalDistinctValues,
  filterNumericRanges: globalNumericRanges,
  filterNumericRangeLoading: globalNumericRangeLoading,
  filterNumericRangeErrors: globalNumericRangeErrors,
  filterResetKey: mapColorMapScopeKey,
  searchFilterOptions: searchGlobalFilterOptions,
  requestSamplingExtraFilterRange,
  openGlobalFilterModal,
});

watch(
  () => [
    props.variant ?? "preview",
    props.datasetId ?? "",
    props.collectionId ?? "",
    props.collectionRevisionId ?? "",
    props.inspectionTime,
    props.waferKey,
  ],
  (scope, previousScope) => {
    if (!previousScope || scope.every((value, index) => value === previousScope[index])) return;
    if (props.globalFilter === undefined) {
      localGlobalFilter.value = emptyScGlobalFilter();
    }
    globalFilterModalVisible.value = false;
    globalDistinctValues.value = {};
    globalNumericRanges.value = {};
    globalNumericRangeLoading.value = {};
    globalNumericRangeErrors.value = {};
    globalFilterSearchVersions.clear();
    globalRangeVersions.clear();
    activeMapTab.value = "wafer";
    mapZoomByMode.value = emptyMapZoomByMode();
    reticleOptions.value = normalizeReticleMapOptions(DEFAULT_RETICLE_MAP_OPTIONS);
    legendGroupBy.value = null;
    hiddenLegendKeysBySource.value = emptyHiddenLegendKeysBySource();
    tableFilter.value = {};
    tableSort.value = null;
    localSelectedDefectIds.value = [];
    mapSelectionQueue.clear();
    model.setTableSelection({ kind: "ids", ids: [] });
    model.setReviewMode(false);
    clearGalleryRandomSamplingIfActive();
    mapSelectionResetVersion.value += 1;
  },
  { flush: "sync" },
);

const selectedDefectIdsModel = computed(() =>
  props.selectedDefectIds === undefined
    ? localSelectedDefectIds.value
    : props.selectedDefectIds.map(String),
);
const blinkHighlightIds = computed(() => new Set(selectedDefectIdsModel.value));
const userFacingMapError = computed(() => model.mapError.value);

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

const galleryHighlightDefectIds = computed(() => {
  const ids = [...blinkHighlightIds.value].map(Number).filter(Number.isFinite);
  return ids.length <= HIGHLIGHT_MAX_DEFECTS ? ids : [];
});
const mapSelectionResetVersion = ref(0);
const mapSelectionQueue = useMapSelectionQueue();

watch(
  () => model.mapLegendColumn.value,
  (column, previousColumn) => {
    if (column !== previousColumn) mapSelectionQueue.prune(activeHiddenLegendKeys.value);
  },
);

onUnmounted(() => {
  mapSelectionQueue.dispose();
});

const barChartItems = computed(() => {
  const groups = model.legendGroups.value ?? {};
  return Object.entries(groups)
    .map(([key, group]) => ({
      key,
      count: Number(group.count ?? group.defectIds.length),
    }))
    .sort((a, b) => String(a.key).localeCompare(String(b.key), undefined, { numeric: true }));
});
const selectedBarChartKey = ref<string | null>(null);
const barChartOption = computed<EChartsOption>(() => ({
  animation: false,
  grid: { left: 42, right: 18, top: 12, bottom: 42 },
  tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
  xAxis: {
    type: "category",
    data: barChartItems.value.map((item) => item.key),
    axisLabel: { color: "rgba(120,120,120,0.9)", fontSize: 10 },
    axisTick: { show: false },
    axisLine: { show: false },
  },
  yAxis: {
    type: "value",
    axisLabel: { color: "rgba(120,120,120,0.8)", fontSize: 10 },
    splitLine: { lineStyle: { color: "rgba(128,128,128,0.15)" } },
  },
  series: [
    {
      type: "bar",
      data: barChartItems.value.map((item) => ({
        value: item.count,
        itemStyle: {
          color: "#4c80f0",
          borderColor: selectedBarChartKey.value === item.key ? "#2457c5" : "transparent",
          borderWidth: selectedBarChartKey.value === item.key ? 2 : 0,
          opacity:
            selectedBarChartKey.value === null || selectedBarChartKey.value === item.key ? 1 : 0.35,
        },
      })),
      barMaxWidth: 18,
      itemStyle: { borderRadius: [3, 3, 0, 0] },
      cursor: "pointer",
    },
  ],
}));
const quadStyle = computed(() => ({
  gridTemplateColumns: isReclassify.value
    ? `${columnPct.value}fr 12px ${100 - RECLASSIFY_ANNOTATION_PCT - columnPct.value}fr 12px ${RECLASSIFY_ANNOTATION_PCT}fr`
    : `${columnPct.value}fr 12px ${100 - columnPct.value}fr`,
}));
const leftPanelStyle = computed(() => ({
  gridTemplateRows: props.globalFilterTriggerTarget
    ? `${mapPct.value}fr 10px ${100 - mapPct.value}fr`
    : `auto ${mapPct.value}fr 10px ${100 - mapPct.value}fr`,
}));
const rightPanelStyle = computed(() =>
  isReclassify.value
    ? { gridTemplateRows: `${barPct.value}fr 10px ${100 - barPct.value}fr` }
    : undefined,
);
const barLegendSource = computed<ScLegendSource>({
  get: () => legendGroupBy.value ?? enabledLegendSources.value[0] ?? "class",
  set: handleLegendGroupByChange,
});
const legendSourceOptions = computed(() => {
  const labels: Record<ScLegendSource, string> = {
    class: "Class",
    bin: "Rough Bin",
    annotation: "Annotation",
    prediction: "Prediction",
    final_class: "Final Class",
  };
  return enabledLegendSources.value.map((source) => ({ label: labels[source], value: source }));
});

watch(legendGroupBy, () => {
  selectedBarChartKey.value = null;
});

async function searchGlobalFilterOptions(payload: {
  field: string;
  search: string;
}): Promise<void> {
  const version = (globalFilterSearchVersions.get(payload.field) ?? 0) + 1;
  globalFilterSearchVersions.set(payload.field, version);
  const values = await model.loadGlobalDistinctValues(payload.field, payload.search);
  if (globalFilterSearchVersions.get(payload.field) !== version) return;
  globalDistinctValues.value = { ...globalDistinctValues.value, [payload.field]: values };
}

async function requestGlobalFilterRange(payload: {
  field: string;
  itemId?: string;
}): Promise<void> {
  const requestKey = payload.itemId ?? `draft:${payload.field}`;
  const version = (globalRangeVersions.get(requestKey) ?? 0) + 1;
  globalRangeVersions.set(requestKey, version);
  globalNumericRangeLoading.value = {
    ...globalNumericRangeLoading.value,
    [requestKey]: true,
  };
  globalNumericRangeErrors.value = {
    ...globalNumericRangeErrors.value,
    [requestKey]: false,
  };
  try {
    const range = await model.loadGlobalNumericRange(payload.field, payload.itemId);
    if (globalRangeVersions.get(requestKey) !== version) return;
    globalNumericRanges.value = { ...globalNumericRanges.value, [requestKey]: range };
  } catch (error) {
    if (globalRangeVersions.get(requestKey) !== version) return;
    globalNumericRangeErrors.value = { ...globalNumericRangeErrors.value, [requestKey]: true };
    reportDataError(`Global filter range query failed for ${payload.field}`, error);
  } finally {
    if (globalRangeVersions.get(requestKey) === version) {
      globalNumericRangeLoading.value = {
        ...globalNumericRangeLoading.value,
        [requestKey]: false,
      };
    }
  }
}

async function requestSamplingExtraFilterRange(
  filter: ScGlobalFilter,
  payload: { field: string; itemId?: string },
): Promise<void> {
  const requestKey = payload.itemId ?? `sampling-draft:${payload.field}`;
  const version = (globalRangeVersions.get(requestKey) ?? 0) + 1;
  globalRangeVersions.set(requestKey, version);
  globalNumericRangeLoading.value = {
    ...globalNumericRangeLoading.value,
    [requestKey]: true,
  };
  globalNumericRangeErrors.value = {
    ...globalNumericRangeErrors.value,
    [requestKey]: false,
  };
  try {
    const range = await model.loadFilterNumericRange(filter, payload.field, payload.itemId);
    if (globalRangeVersions.get(requestKey) !== version) return;
    globalNumericRanges.value = { ...globalNumericRanges.value, [requestKey]: range };
  } catch (error) {
    if (globalRangeVersions.get(requestKey) !== version) return;
    globalNumericRangeErrors.value = { ...globalNumericRangeErrors.value, [requestKey]: true };
    reportDataError(`Extra filter range query failed for ${payload.field}`, error);
  } finally {
    if (globalRangeVersions.get(requestKey) === version) {
      globalNumericRangeLoading.value = {
        ...globalNumericRangeLoading.value,
        [requestKey]: false,
      };
    }
  }
}

function onColumnResizeStart(e: PointerEvent): void {
  e.preventDefault();
  if (e.currentTarget instanceof Element) e.currentTarget.setPointerCapture(e.pointerId);
  isColumnResizing.value = true;
}
function onColumnResizeMove(e: PointerEvent): void {
  if (!isColumnResizing.value || !quadEl.value) return;
  const rect = quadEl.value.getBoundingClientRect();
  if (rect.width <= 0) return;
  columnPct.value = clamp(
    ((e.clientX - rect.left) / rect.width) * 100,
    20,
    isReclassify.value ? 65 : 80,
  );
}
function onColumnResizeEnd(e: PointerEvent): void {
  if (!isColumnResizing.value) return;
  isColumnResizing.value = false;
  if (e.currentTarget instanceof Element) e.currentTarget.releasePointerCapture(e.pointerId);
}
function onRowResizeStart(e: PointerEvent): void {
  e.preventDefault();
  if (e.currentTarget instanceof Element) e.currentTarget.setPointerCapture(e.pointerId);
  isRowResizing.value = true;
}
function onRowResizeMove(e: PointerEvent): void {
  if (!isRowResizing.value || !leftPanelEl.value) return;
  const rect = leftPanelEl.value.getBoundingClientRect();
  if (rect.height <= 0) return;
  mapPct.value = clamp(((e.clientY - rect.top) / rect.height) * 100, 25, 75);
}
function onRowResizeEnd(e: PointerEvent): void {
  if (!isRowResizing.value) return;
  isRowResizing.value = false;
  if (e.currentTarget instanceof Element) e.currentTarget.releasePointerCapture(e.pointerId);
}
function onBarResizeStart(e: PointerEvent): void {
  e.preventDefault();
  if (e.currentTarget instanceof Element) e.currentTarget.setPointerCapture(e.pointerId);
  isBarResizing.value = true;
}
function onBarResizeMove(e: PointerEvent): void {
  if (!isBarResizing.value || !rightPanelEl.value) return;
  const rect = rightPanelEl.value.getBoundingClientRect();
  if (rect.height <= 0) return;
  barPct.value = clamp(((e.clientY - rect.top) / rect.height) * 100, 15, 85);
}
function onBarResizeEnd(e: PointerEvent): void {
  if (!isBarResizing.value) return;
  isBarResizing.value = false;
  if (e.currentTarget instanceof Element) e.currentTarget.releasePointerCapture(e.pointerId);
}

function handleBoxSelect(region: ScMapRegion): void {
  selectedBarChartKey.value = null;
  mapSelectionQueue.append({ kind: "box", mode: activeMapTab.value, region });
}
function handleLassoSelect(selection: ScMapLassoSelection): void {
  selectedBarChartKey.value = null;
  mapSelectionQueue.append({
    kind: "lasso",
    mode: activeMapTab.value,
    selection,
    region: selection.region,
  });
}
function handleLegendSelection(key: string | number | null): void {
  selectedBarChartKey.value = null;
  mapSelectionQueue.replace("legend", key);
}
function handleClearMapSelection(): void {
  selectedBarChartKey.value = null;
  mapSelectionResetVersion.value += 1;
  mapSelectionQueue.clear();
}

function updateLocalSelection(action: ScSelectionAction): void {
  if (action.mode === "replace") {
    localSelectedDefectIds.value = [...new Set(action.ids)];
    return;
  }
  const selected = new Set(localSelectedDefectIds.value);
  for (const id of action.ids) {
    if (action.mode === "add") selected.add(id);
    else if (selected.has(id)) selected.delete(id);
    else selected.add(id);
  }
  localSelectedDefectIds.value = [...selected];
}

function publishSelection(action: ScSelectionAction): void {
  if (props.selectedDefectIds === undefined) {
    updateLocalSelection(action);
    return;
  }
  emit("selection-change", action);
}

function handleTableSelectionChange(selection: ScTableSelectionConstraint): void {
  model.setTableSelection(selection);
}
function handleTableSortChange(sort: { field: string; direction: "asc" | "desc" | null }): void {
  tableSort.value = sort.direction ? { field: sort.field, direction: sort.direction } : null;
}
function handleGallerySelection(
  ids: string[],
  modifiers: {
    ctrl: boolean;
    meta: boolean;
    selectionMode?: "replace" | "add" | "toggle";
  },
): void {
  publishSelection({
    source: "blink-table",
    ids,
    mode: modifiers.selectionMode ?? (modifiers.ctrl || modifiers.meta ? "toggle" : "replace"),
  });
}
function retryMapQuery(): void {
  void model.retryMap();
}
function selectBarChartGroup(key: string | null): void {
  selectedBarChartKey.value = key;
  mapSelectionQueue.replace("bar-chart", key);
}
function handleBarChartClick(event: ECElementEvent): void {
  const item = barChartItems.value[typeof event.dataIndex === "number" ? event.dataIndex : -1];
  if (!item) return;
  selectBarChartGroup(selectedBarChartKey.value === item.key ? null : item.key);
}

function useMapSelectionQueue() {
  let replacementVersion = 0;
  let queue = Promise.resolve();
  let visibilityQueue = Promise.resolve();
  let visibilityEpoch = 0;
  let disposed = false;

  function enqueue(operation: () => Promise<void>, failureReason: string): Promise<void> {
    queue = queue
      .then(async () => {
        if (!disposed) await operation();
      })
      .catch((error: unknown) => {
        reportDataError(failureReason, error);
      });
    return queue;
  }

  async function updateSelection(command: ScMapSelectionCommand): Promise<number[]> {
    const panel = mapPanel.value;
    if (!panel) throw new Error("Map panel is not ready");
    return panel.updateMapSelection(command);
  }

  function append(selection: QueuedAreaSelection): void {
    const version = replacementVersion;
    const hiddenLegendKeys = [...activeHiddenLegendKeys.value];
    enqueue(async () => {
      if (version !== replacementVersion) return;
      const selectedIds = await updateSelection({
        operation: "append",
        hiddenLegendKeys,
        constraint:
          selection.kind === "lasso"
            ? {
                kind: "polygon",
                mode: selection.mode,
                points: selection.selection.points,
                region: selection.region,
              }
            : { kind: "rectangle", mode: selection.mode, region: selection.region },
      });
      if (version !== replacementVersion) return;
      model.applyMapSelection(selectedIds);
    }, `${selection.kind} selection failed`);
  }

  function replace(source: "legend" | "bar-chart", key: string | number | null): void {
    const version = ++replacementVersion;
    const hiddenLegendKeys = [...activeHiddenLegendKeys.value];
    // Replacement actions supersede slow area queries immediately. Model
    // Selection mutations remain serialized by the workbench model.
    queue = Promise.resolve();
    enqueue(async () => {
      if (version !== replacementVersion) return;
      if (key === null) {
        mapPanel.value?.clearMapSelection();
        model.applyMapSelection([]);
        return;
      }
      const ids = await updateSelection({
        operation: "replace",
        hiddenLegendKeys,
        constraint: { kind: "legend", key: String(key) },
      });
      if (version !== replacementVersion) return;
      model.applyMapSelection(ids);
    }, `${source} selection failed`);
  }

  function prune(hiddenLegendKeys: readonly string[]): void {
    const version = ++replacementVersion;
    const epoch = visibilityEpoch;
    const hiddenKeys = [...hiddenLegendKeys];
    queue = Promise.resolve();
    visibilityQueue = visibilityQueue
      .then(async () => {
        if (disposed || epoch !== visibilityEpoch) return;
        let visibleIds: number[];
        try {
          visibleIds = await updateSelection({
            operation: "prune",
            hiddenLegendKeys: hiddenKeys,
          });
        } catch (error) {
          if (!disposed && epoch === visibilityEpoch) {
            model.clearMapSelection();
            mapPanel.value?.clearMapSelection();
            mapSelectionResetVersion.value += 1;
          }
          throw error;
        }
        if (disposed || epoch !== visibilityEpoch || version !== replacementVersion) return;
        model.applyMapSelection(visibleIds);
        selectedBarChartKey.value = null;
        mapSelectionResetVersion.value += 1;
      })
      .catch((error: unknown) => {
        if (!disposed && epoch === visibilityEpoch) {
          reportDataError("Prune map selection to visible legend values failed", error);
        }
      });
  }

  function invert(): void {
    void prepareContextAction().then((ready) => {
      if (!ready) return;
      const version = replacementVersion;
      const hiddenLegendKeys = [...activeHiddenLegendKeys.value];
      enqueue(async () => {
        if (version !== replacementVersion) return;
        const inverted = await updateSelection({
          operation: "invert",
          hiddenLegendKeys,
        });
        if (version !== replacementVersion) return;
        model.applyMapSelection(inverted);
        selectedBarChartKey.value = null;
        mapSelectionResetVersion.value += 1;
      }, "Invert map selection failed");
    });
  }

  function clear(): void {
    replacementVersion += 1;
    visibilityEpoch += 1;
    queue = Promise.resolve();
    visibilityQueue = Promise.resolve();
    model.clearMapSelection();
    mapPanel.value?.clearMapSelection();
  }

  function dispose(): void {
    disposed = true;
    replacementVersion += 1;
    visibilityEpoch += 1;
  }

  async function prepareContextAction(): Promise<boolean> {
    const epoch = visibilityEpoch;
    while (true) {
      const pendingVisibility = visibilityQueue;
      await pendingVisibility;
      if (disposed || epoch !== visibilityEpoch) return false;
      if (pendingVisibility === visibilityQueue) break;
    }
    replacementVersion += 1;
    queue = Promise.resolve();
    return true;
  }

  return { append, replace, prune, invert, clear, dispose, prepareContextAction };
}
</script>

<template>
  <div
    ref="quadEl"
    class="iq-quad"
    :class="{
      'iq-quad--column-resizing': isColumnResizing,
      'iq-quad--row-resizing': isRowResizing,
      'iq-quad--bar-resizing': isBarResizing,
      'iq-quad--reclassify': isReclassify,
    }"
    :style="quadStyle"
  >
    <ScGlobalFilterModal
      v-model:show="globalFilterModalVisible"
      :filter="globalFilterModel"
      :columns="sampleTableColumns"
      :distinct-values="globalDistinctValues"
      :numeric-ranges="globalNumericRanges"
      :numeric-range-loading="globalNumericRangeLoading"
      :numeric-range-errors="globalNumericRangeErrors"
      :show-reclassify-columns="isReclassify"
      :reset-key="mapColorMapScopeKey"
      @update:filter="handleGlobalFilterApply"
      @search-options="searchGlobalFilterOptions"
      @request-range="requestGlobalFilterRange"
    />
    <div ref="leftPanelEl" class="iq-panel-left" :style="leftPanelStyle">
      <Teleport :to="globalFilterTriggerTarget ?? 'body'" :disabled="!globalFilterTriggerTarget">
        <div
          class="iq-global-filter-toolbar"
          :class="{ 'iq-global-filter-toolbar--external': globalFilterTriggerTarget }"
        >
          <NButton
            data-testid="sc-global-filter-trigger"
            size="small"
            :type="globalFilterCount > 0 ? 'primary' : 'default'"
            @click="globalFilterModalVisible = true"
          >
            Global Filter{{ globalFilterCount > 0 ? ` (${globalFilterCount})` : "" }}
          </NButton>
          <NButton
            v-if="model.mapSelectedDefectIds.value.length > 0"
            data-testid="sc-clear-map-selection-filter"
            size="small"
            secondary
            @click="handleClearMapSelection"
          >
            Map selection ({{ model.mapSelectedDefectIds.value.length }}) ×
          </NButton>
          <NButton
            v-if="tableFilterCount > 0"
            data-testid="sc-clear-table-filters"
            size="small"
            secondary
            @click="clearTableFilters"
          >
            Table filters ({{ tableFilterCount }}) ×
          </NButton>
          <NButton
            v-if="samplingCohortCount > 0"
            data-testid="sc-clear-sampling-cohort"
            size="small"
            secondary
            @click="clearGalleryRandomSamplingIfActive"
          >
            Sampling cohort ({{ samplingCohortCount }}) ×
          </NButton>
        </div>
      </Teleport>
      <div class="iq-wafer">
        <ScMapPanelBinned
          ref="mapPanel"
          :active-map-tab="activeMapTab"
          :arrow-data="model.mapArrowData.value"
          :map-legend-column="model.mapLegendColumn.value"
          :legend-groups="model.legendGroups.value"
          :wafer-geometry="waferGeometryModel"
          :wafer-radius-nm="waferGeometryModel?.waferRadiusNm ?? undefined"
          :reticle-die-size-x="reticleDieSizeX"
          :reticle-die-size-y="reticleDieSizeY"
          :reticle-options="reticleOptions"
          :legend-group-by="legendGroupBy"
          :legend-sources="enabledLegendSources"
          :color-map-scope-key="mapColorMapScopeKey"
          :zoom="zoom"
          :map-selection-count="model.mapSelectedDefectIds.value.length"
          :highlight-defect-ids="galleryHighlightDefectIds"
          :selection-defect-ids="model.mapSelectedDefectIds.value"
          :selection-reset-version="mapSelectionResetVersion"
          :map-loading="model.activeMapLoading.value || !dataReady"
          :map-error="userFacingMapError"
          :map-progress-message="
            dataReady ? model.mapProgressMessage.value : 'Connecting to data service...'
          "
          :map-progress-percent="dataReady ? model.mapProgressPercent.value : 0"
          @update:active-map-tab="handleActiveMapTabChange"
          @update:reticle-options="handleReticleOptionsChange"
          @commit-map-selection-filter="commitMapSelectionFilter"
          @invert-map-selection-mode="handleInvertMapSelectionMode"
          @copy-selected-defect-ids="handleCopySelectedDefectIds"
          @clear-selection="handleClearMapSelection"
          @legend-select="handleLegendSelection"
          @legend-group-change="handleLegendGroupByChange"
          @legend-hidden-change="handleLegendHiddenChange"
          @zoom-in="handleMapZoomChange"
          @box-select="handleBoxSelect"
          @lasso-select="handleLassoSelect"
          @retry="retryMapQuery"
        />
      </div>
      <div
        class="iq-splitter iq-splitter--row"
        role="separator"
        aria-orientation="horizontal"
        @pointerdown="onRowResizeStart"
        @pointermove="onRowResizeMove"
        @pointerup="onRowResizeEnd"
        @pointercancel="onRowResizeEnd"
      />
      <ScSampleTable
        v-if="model.sampleTableDataSource.value"
        :data-source="model.sampleTableDataSource.value"
        :loading="!dataReady"
        :selection="model.tableSelection.value"
        :filter="tableFilter"
        :sort="tableSort"
        :show-reclassify-columns="isReclassify"
        :enable-selection="true"
        @selection-change="handleTableSelectionChange"
        @filter-change="handleTableFilterChange"
        @sort-change="handleTableSortChange"
      />
    </div>
    <div
      class="iq-splitter iq-splitter--column"
      role="separator"
      aria-orientation="vertical"
      @pointerdown="onColumnResizeStart"
      @pointermove="onColumnResizeMove"
      @pointerup="onColumnResizeEnd"
      @pointercancel="onColumnResizeEnd"
    />
    <div
      ref="rightPanelEl"
      class="iq-panel-right"
      :class="{ 'iq-panel-right--split': isReclassify }"
      :style="rightPanelStyle"
    >
      <div class="iq-blink-pane">
        <ScBlinkVirtualTable
          :data-source="workbench.dataSource.value"
          :gallery-query="model.galleryQuery.value"
          :loading="model.galleryLoading.value"
          :dataset-id="datasetId"
          :selected-defect-ids="blinkHighlightIds"
          :inspection-time="inspectionTime"
          :wafer-key="waferKey"
          :show-prediction-badges="isReclassify"
          :annotation-drafts="annotationDrafts"
          @mode-change="handleReviewModeChange"
          @select-samples="handleGallerySelection"
        />
      </div>
      <div
        v-if="isReclassify"
        class="iq-splitter iq-splitter--row iq-splitter--bar"
        role="separator"
        aria-orientation="horizontal"
        @pointerdown="onBarResizeStart"
        @pointermove="onBarResizeMove"
        @pointerup="onBarResizeEnd"
        @pointercancel="onBarResizeEnd"
      />
      <div v-if="isReclassify" class="iq-bar-pane">
        <div class="iq-bar-header">
          <div class="iq-bar-title">Group Distribution</div>
          <NSelect
            v-model:value="barLegendSource"
            size="tiny"
            :options="legendSourceOptions"
            class="iq-bar-source"
          />
        </div>
        <VChart
          class="iq-bar-chart"
          :option="barChartOption"
          autoresize
          @click="handleBarChartClick"
        />
      </div>
    </div>
    <template v-if="isReclassify"
      ><div class="iq-splitter iq-splitter--column" role="separator" aria-orientation="vertical" />
      <div class="iq-panel-annotation"><slot name="annotation" /></div
    ></template>
  </div>
</template>

<style scoped>
.iq-quad {
  position: relative;
  flex: 1;
  min-height: 0;
  min-width: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr);
  gap: 0;
  overflow: hidden;
}
.iq-quad--column-resizing {
  cursor: col-resize;
}
.iq-quad--row-resizing,
.iq-quad--bar-resizing {
  cursor: row-resize;
}
.iq-quad--column-resizing,
.iq-quad--row-resizing,
.iq-quad--bar-resizing {
  user-select: none;
}
.iq-panel-left {
  display: grid;
  min-height: 0;
  overflow: hidden;
}
.iq-global-filter-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-start;
  padding: 0 0 8px;
}
.iq-global-filter-toolbar--external {
  padding: 0;
}
.iq-panel-right {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
.iq-panel-right--split {
  display: grid;
  gap: 0;
}
.iq-splitter {
  position: relative;
  z-index: 2;
  flex: none;
  touch-action: none;
}
.iq-splitter::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: 999px;
  background: transparent;
  transition: background-color 0.12s ease;
}
.iq-splitter:hover::before,
.iq-quad--column-resizing .iq-splitter--column::before,
.iq-quad--row-resizing .iq-splitter--row::before,
.iq-quad--bar-resizing .iq-splitter--bar::before {
  background: var(--cv-primary, rgba(76, 128, 240, 0.45));
}
.iq-splitter--column {
  width: 12px;
  cursor: col-resize;
}
.iq-splitter--column::before {
  left: 5px;
  right: 5px;
}
.iq-splitter--row {
  height: 10px;
  cursor: row-resize;
}
.iq-splitter--row::before {
  top: 4px;
  bottom: 4px;
}
.iq-wafer,
.iq-bar-pane {
  min-height: 0;
  overflow: hidden;
  background: var(--cv-card-bg, #1a1a2e);
  border: 1px solid var(--cv-border, rgba(255, 255, 255, 0.1));
  border-radius: 8px;
  padding: 8px 10px;
}
.iq-wafer {
  flex: 1 1 0;
  width: 100%;
  display: flex;
  flex-direction: column;
}
.iq-blink-pane {
  display: flex;
  min-height: 0;
  overflow: hidden;
}
.iq-panel-right > *,
.iq-blink-pane > * {
  flex: 1;
  min-height: 0;
}
.iq-bar-pane {
  grid-row: 3;
  display: flex;
  flex-direction: column;
}
.iq-bar-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
  margin-bottom: 6px;
}
.iq-bar-title {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.65));
}
.iq-bar-source {
  width: 112px;
  flex: 0 0 112px;
}
.iq-bar-chart {
  flex: 1;
  min-height: 0;
  width: 100%;
}
.iq-panel-annotation {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
</style>
