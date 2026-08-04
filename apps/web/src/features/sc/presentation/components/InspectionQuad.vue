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
import type { ScMapLassoSelection } from "@platform/sc-map-element";
import ScMapPanelBinned from "@/features/sc/presentation/components/ScMapPanelBinned.vue";
import ScGlobalFilterModal from "@/features/sc/presentation/components/ScGlobalFilterModal.vue";
import ScSampleTable from "@/features/sc/presentation/components/ScSampleTable.vue";
import ScBlinkVirtualTable from "@/features/sc/presentation/components/ScBlinkVirtualTable.vue";
import type { ScSampleTableFilter, ScSampleTableSort } from "@/features/sc/domain/sampleTable";
import type { ScTableSelectionConstraint } from "@/features/sc/domain/workbenchDataSource";
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
import { useInspectionQuadData } from "@/features/sc/presentation/composables/useInspectionQuadData";
import type { ScSamplingCandidateOptions } from "@/features/sc/presentation/composables/useSqlInspectionModel";

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

const props = defineProps<{
  variant?: "preview" | "reclassify";
  datasetId?: string;
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
  globalFilterTriggerTarget?: string;
}>();

const emit = defineEmits<{
  (e: "clear-gallery-random-sampling"): void;
  (e: "selection-change", action: ScSelectionAction): void;
}>();

const DEFAULT_COLUMN_PCT = 35;
const RECLASSIFY_ANNOTATION_PCT = 15;
const DEFAULT_MAP_PCT = 55;
const DEFAULT_BAR_PCT = 60;
const DEFAULT_RETICLE_DIE_SIZE = 100_000;
type MapMode = "wafer" | "die" | "reticle";
type MapViewport = { x: number; y: number; w: number; h: number };
const quadEl = ref<HTMLElement | null>(null);
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
// Merge note for the follow-up workbench redesign: 89ae5235 kept global/table
// filters and several map controls in ReclassifyPage. They are intentionally
// local now because their controls and consumers all belong to this workbench.
// Parent workflows may read a cloned GlobalFilter snapshot, but must not mirror
// workbench-local state through props/events again.
const globalFilter = ref<ScSampleTableFilter>({});
const globalFilterModalVisible = ref(false);
const activeMapTab = ref<MapMode>("wafer");
const mapZoomByMode = ref<Record<MapMode, MapViewport | null>>(emptyMapZoomByMode());
const zoom = computed(() => mapZoomByMode.value[activeMapTab.value]);
const reticleOptions = ref<ReticleMapOptions>(
  normalizeReticleMapOptions(DEFAULT_RETICLE_MAP_OPTIONS),
);
const legendGroupBy = ref<ScLegendSource | null>(null);
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
const globalFilterModel = computed(() => globalFilter.value);
const globalFilterCount = computed(() => Object.keys(globalFilter.value).length);
const enabledLegendSources = computed<ScLegendSource[]>(() =>
  isReclassify.value
    ? ["class", "bin", "annotation", "prediction", "final_class"]
    : ["class", "bin"],
);
const mapColorMapScopeKey = computed(() =>
  props.datasetId
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
  inspectionTime: computed(() => props.inspectionTime),
  waferKey: computed(() => props.waferKey),
  legendGroupBy: computed(() => legendGroupBy.value),
  globalFilter: globalFilterModel,
  tableFilter: computed(() => tableFilter.value),
  tableSort: computed(() => tableSort.value),
  reticle: reticleProjectionModel,
  galleryRandomSamplingDefectIds: computed(() => props.galleryRandomSamplingDefectIds),
});

async function querySamplingCandidateCount(options: ScSamplingCandidateOptions): Promise<number> {
  return model.querySamplingCandidateCount(options);
}

async function querySamplingDefectIds(
  count: number,
  seed: number,
  options: ScSamplingCandidateOptions,
): Promise<number[]> {
  return model.querySamplingDefectIds(count, seed, options);
}

function getSamplingContext(): { reviewMode: boolean; mapSelectionCount: number } {
  return {
    reviewMode: model.reviewMode.value,
    mapSelectionCount: model.mapSelectedDefectIds.value.length,
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

function getGlobalFilter(): ScSampleTableFilter {
  return cloneSampleTableFilter(globalFilter.value);
}

function clearGalleryRandomSamplingIfActive(): void {
  if (props.galleryRandomSamplingDefectIds?.size) emit("clear-gallery-random-sampling");
}

function handleGlobalFilterChange(filter: ScSampleTableFilter): void {
  globalFilter.value = cloneSampleTableFilter(filter);
  clearGalleryRandomSamplingIfActive();
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

function handleMapSelectionModeChange(mode: ScMapSelectionMode): void {
  model.setMapSelectionMode(mode);
  clearGalleryRandomSamplingIfActive();
}

function handleInvertMapSelectionMode(): void {
  model.invertMapSelectionMode();
  clearGalleryRandomSamplingIfActive();
}

function handleUndoMapSelectionMode(): void {
  model.undoMapSelectionMode();
  clearGalleryRandomSamplingIfActive();
}

async function handleCopySelectedDefectIds(): Promise<void> {
  try {
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
  if (Object.keys(filter).length > 0) clearGalleryRandomSamplingIfActive();
}

function handleReviewModeChange(mode: "patch" | "review"): void {
  const nextReviewMode = mode === "review";
  if (model.reviewMode.value !== nextReviewMode) clearGalleryRandomSamplingIfActive();
  model.setReviewMode(nextReviewMode);
}

defineExpose({
  getGlobalFilter,
  getSamplingContext,
  querySamplingCandidateCount,
  querySamplingDefectIds,
});

watch(
  () => [props.variant ?? "preview", props.datasetId ?? "", props.inspectionTime, props.waferKey],
  (scope, previousScope) => {
    if (!previousScope || scope.every((value, index) => value === previousScope[index])) return;
    globalFilter.value = {};
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
    tableFilter.value = {};
    tableSort.value = null;
    localSelectedDefectIds.value = [];
    model.resetMapSelectionMode();
    void model.clearMapSelection();
    model.setTableSelection({ kind: "ids", ids: [] });
    clearGalleryRandomSamplingIfActive();
  },
  { flush: "sync" },
);

const selectedDefectIdsModel = computed(() =>
  props.selectedDefectIds === undefined
    ? localSelectedDefectIds.value
    : props.selectedDefectIds.map(String),
);
const blinkHighlightIds = computed(() => new Set(selectedDefectIdsModel.value));
const userFacingMapError = computed(() => {
  if (model.mapError.value) return "Map data could not be loaded. Try again.";
  return null;
});

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

const galleryHighlightDefectIds = computed(() => {
  const ids = [...blinkHighlightIds.value].map(Number).filter(Number.isFinite);
  return ids.length <= HIGHLIGHT_MAX_DEFECTS ? ids : [];
});
const mapImmediateCrosshairDefectIds = ref<number[]>([]);
const mapImmediateCrosshairVersion = ref(0);
const mapSelectionQueue = useMapSelectionQueue();

function refreshImmediateCrosshairFromMapSelection(): void {
  mapImmediateCrosshairDefectIds.value = [];
  mapImmediateCrosshairVersion.value += 1;
  const ids = model.mapSelectedDefectIds.value;
  if (ids.length === 0 || ids.length > HIGHLIGHT_MAX_DEFECTS) return;
  mapImmediateCrosshairDefectIds.value = [...ids];
  mapImmediateCrosshairVersion.value += 1;
}

watch([activeMapTab, zoom], () => {
  refreshImmediateCrosshairFromMapSelection();
});

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

async function requestGlobalFilterRange(field: string): Promise<void> {
  const version = (globalRangeVersions.get(field) ?? 0) + 1;
  globalRangeVersions.set(field, version);
  globalNumericRangeLoading.value = { ...globalNumericRangeLoading.value, [field]: true };
  globalNumericRangeErrors.value = { ...globalNumericRangeErrors.value, [field]: false };
  try {
    const range = await model.loadGlobalNumericRange(field);
    if (globalRangeVersions.get(field) !== version) return;
    globalNumericRanges.value = { ...globalNumericRanges.value, [field]: range };
  } catch (error) {
    if (globalRangeVersions.get(field) !== version) return;
    globalNumericRangeErrors.value = { ...globalNumericRangeErrors.value, [field]: true };
    reportDataError(`Global filter range query failed for ${field}`, error);
  } finally {
    if (globalRangeVersions.get(field) === version) {
      globalNumericRangeLoading.value = { ...globalNumericRangeLoading.value, [field]: false };
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
  mapImmediateCrosshairDefectIds.value = [];
  mapSelectionQueue.append({ kind: "box", mode: activeMapTab.value, region });
}
function handleLassoSelect(selection: ScMapLassoSelection): void {
  selectedBarChartKey.value = null;
  mapImmediateCrosshairDefectIds.value = [];
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
  mapImmediateCrosshairDefectIds.value = [];
  mapImmediateCrosshairVersion.value += 1;
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
  let disposed = false;

  function enqueue(operation: () => Promise<void>, failureReason: string): void {
    queue = queue
      .then(async () => {
        if (!disposed) await operation();
      })
      .catch((error: unknown) => {
        reportDataError(failureReason, error);
      });
  }

  function append(selection: QueuedAreaSelection): void {
    const version = replacementVersion;
    enqueue(async () => {
      if (version !== replacementVersion) return;
      const selectedIds =
        selection.kind === "lasso"
          ? await model.queryLassoSelection(selection.mode, selection.selection)
          : await model.queryBoxSelection(selection.mode, selection.region);
      if (version !== replacementVersion || selectedIds.length === 0) return;
      await model.appendMapSelection(selectedIds);
      if (version !== replacementVersion) return;
      clearGalleryRandomSamplingIfActive();
    }, `${selection.kind} selection failed`);
  }

  function replace(source: "legend" | "bar-chart", key: string | number | null): void {
    const version = ++replacementVersion;
    // Replacement actions supersede slow area queries immediately. Model
    // Selection mutations remain serialized by the workbench model.
    queue = Promise.resolve();
    enqueue(async () => {
      if (version !== replacementVersion) return;
      const ids = key === null ? [] : await model.queryLegendSelection(key);
      if (version !== replacementVersion) return;
      if (key !== null && ids.length <= HIGHLIGHT_MAX_DEFECTS) {
        mapImmediateCrosshairDefectIds.value = [...ids];
      } else {
        mapImmediateCrosshairDefectIds.value = [];
      }
      if (version !== replacementVersion) return;
      mapImmediateCrosshairVersion.value += 1;
      await model.applyMapSelection(ids);
      if (version !== replacementVersion) return;
      clearGalleryRandomSamplingIfActive();
    }, `${source} selection failed`);
  }

  function clear(): void {
    const version = ++replacementVersion;
    queue = Promise.resolve();
    enqueue(async () => {
      if (version !== replacementVersion) return;
      await model.clearMapSelection();
      if (version !== replacementVersion) return;
      clearGalleryRandomSamplingIfActive();
    }, "clear map selection failed");
  }

  function dispose(): void {
    disposed = true;
    replacementVersion += 1;
  }

  return { append, replace, clear, dispose };
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
      :distinct-values="globalDistinctValues"
      :numeric-ranges="globalNumericRanges"
      :numeric-range-loading="globalNumericRangeLoading"
      :numeric-range-errors="globalNumericRangeErrors"
      :show-reclassify-columns="isReclassify"
      @update:filter="handleGlobalFilterChange"
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
        </div>
      </Teleport>
      <div class="iq-wafer">
        <ScMapPanelBinned
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
          :map-selection-mode="model.mapSelectionMode.value"
          :map-selection-count="model.mapSelectedDefectIds.value.length"
          :can-undo-map-selection-mode="model.canUndoMapSelectionMode.value"
          :highlight-defect-ids="galleryHighlightDefectIds"
          :immediate-crosshair-defect-ids="mapImmediateCrosshairDefectIds"
          :immediate-crosshair-version="mapImmediateCrosshairVersion"
          :map-loading="model.activeMapLoading.value || !dataReady"
          :map-error="userFacingMapError"
          :map-progress-message="
            dataReady ? model.mapProgressMessage.value : 'Connecting to data service...'
          "
          :map-progress-percent="dataReady ? model.mapProgressPercent.value : 0"
          @update:active-map-tab="handleActiveMapTabChange"
          @update:reticle-options="handleReticleOptionsChange"
          @update:map-selection-mode="handleMapSelectionModeChange"
          @invert-map-selection-mode="handleInvertMapSelectionMode"
          @undo-map-selection-mode="handleUndoMapSelectionMode"
          @copy-selected-defect-ids="handleCopySelectedDefectIds"
          @clear-selection="handleClearMapSelection"
          @legend-select="handleLegendSelection"
          @legend-group-change="handleLegendGroupByChange"
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
