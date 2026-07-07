<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import "@perspective-dev/viewer/inline";
import { NButton, NResult, NSelect } from "naive-ui";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsOption } from "echarts";
import type { ECElementEvent } from "echarts/core";
import ScMapPanelBinned from "@/features/sc/presentation/components/ScMapPanelBinned.vue";
import ScGlobalFilterBar from "@/features/sc/presentation/components/ScGlobalFilterBar.vue";
import ScSampleTable from "@/features/sc/presentation/components/ScSampleTable.vue";
import ScBlinkVirtualTable from "@/features/sc/presentation/components/ScBlinkVirtualTable.vue";
import type { InspectionSummaryItem } from "@/features/sc/domain/models";
import type { ScSampleTableFilter, ScSampleTableSort } from "@/features/sc/domain/sampleTable";
import type { ScLegendSource } from "@/features/sc/domain/workbenchInteraction";
import type { ReticleMapOptions } from "@/features/sc/application/reticleMapOptions";
import type { HighlightDefect } from "@/features/sc/presentation/components/types";
import type { Filter } from "@perspective-dev/client";
import { useScPerspectiveWorkbench } from "@/features/sc/presentation/composables/useScPerspectiveWorkbench";
import { usePerspectiveSampleTableDataSource } from "@/features/sc/presentation/composables/usePerspectiveSampleTableDataSource";
import { usePerspectiveInspectionModel } from "@/features/sc/presentation/composables/usePerspectiveInspectionModel";

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

const props = defineProps<{
  variant?: "preview" | "reclassify";
  datasetId?: string;
  samplesError: string | null;
  inspectionTime: string;
  waferKey: number;
  inspectionItem?: InspectionSummaryItem;
  showPredictionBadges?: boolean;
  annotationDrafts?: Record<string, string>;
  activeMapTab: "wafer" | "die" | "reticle";
  waferGeometry?: {
    waferRadiusNm: number;
    centerX: number;
    centerY: number;
    originX: number;
    originY: number;
    dieSizeX: number;
    dieSizeY: number;
  } | null;
  legendGroupBy?: ScLegendSource | null;
  legendSources?: ScLegendSource[];
  reticleXDieCount?: number;
  reticleYDieCount?: number;
  reticleDieSizeX?: number;
  reticleDieSizeY?: number;
  reticleOptions?: ReticleMapOptions;
  zoom?: { x: number; y: number; w: number; h: number } | null;
  selectedGalleryDefectIds?: Array<number | string>;
  globalFilter?: ScSampleTableFilter;
  tableFilter?: ScSampleTableFilter;
  globalFilterActionEnabled?: boolean;
  tableSort?: ScSampleTableSort | null;
  galleryRandomSamplingDefectIds?: Set<string>;
  syncGallerySelection?: boolean;
}>();

const emit = defineEmits<{
  (e: "update:activeMapTab", v: "wafer" | "die" | "reticle"): void;
  (e: "update:reticleOptions", v: ReticleMapOptions): void;
  (e: "zoom-in", vp: { x: number; y: number; w: number; h: number } | null): void;
  (
    e: "map-filter-change",
    payload: {
      ids: number[];
      region: { x: number; y: number; w: number; h: number };
      key?: string | number | null;
    },
  ): void;
  (e: "table-filter-change", filter: ScSampleTableFilter): void;
  (e: "update:global-filter", filter: ScSampleTableFilter): void;
  (e: "table-apply-filter-as-global", filter: ScSampleTableFilter): void;
  (e: "table-sort-change", sort: { field: string; direction: "asc" | "desc" | null }): void;
  (e: "table-selection-change", ids: number[]): void;
  (e: "legend-group-change", groupBy: string | null): void;
  (e: "clear-gallery-random-sampling"): void;
  (
    e: "select-samples",
    ids: string[],
    modifiers: {
      shift: boolean;
      ctrl: boolean;
      meta: boolean;
      selectionMode?: string;
    },
  ): void;
  (e: "retry"): void;
}>();

const DEFAULT_COLUMN_PCT = 35;
const RECLASSIFY_ANNOTATION_PCT = 15;
const DEFAULT_MAP_PCT = 55;
const DEFAULT_BAR_PCT = 60;
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
type BoxSelectionRegion = { x: number; y: number; w: number; h: number };
type QueuedBoxSelection = {
  mode: "wafer" | "die" | "reticle";
  region: BoxSelectionRegion;
};

const isReclassify = computed(() => props.variant === "reclassify");
const globalFilterModel = computed<ScSampleTableFilter>({
  get: () => props.globalFilter ?? {},
  set: (filter) => emit("update:global-filter", filter),
});
const enabledLegendSources = computed<ScLegendSource[]>(
  () =>
    props.legendSources ??
    (isReclassify.value
      ? ["class", "bin", "annotation", "prediction", "final_class"]
      : ["class", "bin"]),
);
const reticleOptionsModel = computed<ReticleMapOptions>(() => ({
  xDieCount: props.reticleOptions?.xDieCount ?? props.reticleXDieCount ?? 2,
  yDieCount: props.reticleOptions?.yDieCount ?? props.reticleYDieCount ?? 6,
  xDieShift: props.reticleOptions?.xDieShift ?? 0,
  yDieShift: props.reticleOptions?.yDieShift ?? 0,
}));
const reticleDieSizeXModel = computed(
  () => props.reticleDieSizeX ?? props.inspectionItem?.die_size_x ?? 150_000_000,
);
const reticleDieSizeYModel = computed(
  () => props.reticleDieSizeY ?? props.inspectionItem?.die_size_y ?? 150_000_000,
);

const {
  perspective,
  perspectiveReady,
  model,
  tableDataSource,
  reportPerspectiveError,
  dispose: disposePerspectiveQuadData,
} = usePerspectiveQuadData();

const sampleTableTotal = 0;
const tableHighlightIds = computed(
  () => new Set((model.tableSelectedDefectIds.value ?? []).map(Number).filter(Number.isFinite)),
);
const blinkHighlightIds = computed(
  () => new Set((props.selectedGalleryDefectIds ?? []).map(String)),
);
const EMPTY_MAP_DISPLAY = new Float32Array(0);
const activeWaferDisplay = computed(() =>
  props.activeMapTab === "wafer" ? model.waferDisplay.value : EMPTY_MAP_DISPLAY,
);
const activeDieDisplay = computed(() =>
  props.activeMapTab === "die" ? model.dieDisplay.value : EMPTY_MAP_DISPLAY,
);
const activeReticleDisplay = computed(() =>
  props.activeMapTab === "reticle" ? model.reticleDisplay.value : EMPTY_MAP_DISPLAY,
);
const perspectiveMaskVisible = computed(
  () => perspective.reconnecting.value || perspective.reconnectFailed.value,
);
const perspectiveMaskTitle = computed(() =>
  perspective.reconnectFailed.value ? "Perspective connection lost" : "Reconnecting...",
);
const perspectiveMaskDescription = computed(() => {
  if (perspective.reconnectFailed.value) {
    return "Automatic reconnect failed. Try reconnecting manually, or refresh the page.";
  }
  const attempt = perspective.reconnectAttempt.value;
  const maxAttempts = perspective.reconnectMaxAttempts;
  return attempt > 0
    ? `Restoring websocket connection (${attempt}/${maxAttempts})`
    : "Restoring websocket connection";
});

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

const galleryHighlightDefects = ref<HighlightDefect[]>([]);
const highlightDefects = computed<HighlightDefect[]>(() => galleryHighlightDefects.value);
const mapImmediateCrosshairDefects = ref<HighlightDefect[]>([]);
const mapImmediateCrosshairVersion = ref(0);
let mapImmediateCrosshairSeq = 0;
let _highlightTimer: ReturnType<typeof setTimeout> | null = null;
const HIGHLIGHT_DEBOUNCE_MS = 250;
const boxSelectionQueue = useBoxSelectionQueue();

watch(
  () => props.selectedGalleryDefectIds,
  (ids) => {
    if (!props.syncGallerySelection) return;
    void model.setGallerySelectedDefectIds(ids ?? []);
  },
  { immediate: true },
);

function scheduleHighlightUpdate(ids: Set<string>, tab: string): void {
  if (_highlightTimer !== null) clearTimeout(_highlightTimer);
  _highlightTimer = setTimeout(async () => {
    _highlightTimer = null;
    const numericIds = [...ids].map(Number).filter(Number.isFinite);
    if (numericIds.length > HIGHLIGHT_MAX_DEFECTS) {
      galleryHighlightDefects.value = [];
      return;
    }
    if (tab !== props.activeMapTab) return;
    const result = await model.highlightDefectsForIds(numericIds);
    if (tab !== props.activeMapTab) return;
    galleryHighlightDefects.value = result;
  }, HIGHLIGHT_DEBOUNCE_MS);
}

async function refreshImmediateCrosshairFromMapSelection(): Promise<void> {
  const seq = ++mapImmediateCrosshairSeq;
  mapImmediateCrosshairDefects.value = [];
  mapImmediateCrosshairVersion.value += 1;
  const ids = model.mapSelectedDefectIds.value;
  if (ids.length === 0 || ids.length > HIGHLIGHT_MAX_DEFECTS) return;
  const result = await model.highlightDefectsForIds(ids);
  if (seq !== mapImmediateCrosshairSeq) return;
  mapImmediateCrosshairDefects.value = result;
  mapImmediateCrosshairVersion.value += 1;
}

watch(
  () => ({ ids: blinkHighlightIds.value, tab: props.activeMapTab }),
  ({ ids, tab }) => scheduleHighlightUpdate(ids, tab),
  { immediate: true },
);

watch([() => props.activeMapTab, () => props.zoom], () => {
  void refreshImmediateCrosshairFromMapSelection();
});

onUnmounted(() => {
  disposePerspectiveQuadData();
  if (_highlightTimer !== null) clearTimeout(_highlightTimer);
  boxSelectionQueue.clear();
});

const barChartItems = computed(() => {
  const groups = model.legendGroups.value ?? {};
  return Object.entries(groups)
    .map(([key, group]) => ({
      key,
      count: Number(group.count ?? group.defectIds.length),
      defectIds: group.defectIds.map(Number).filter(Number.isFinite),
    }))
    .sort((a, b) => String(a.key).localeCompare(String(b.key), undefined, { numeric: true }));
});
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
      data: barChartItems.value.map((item) => item.count),
      barMaxWidth: 18,
      itemStyle: { color: "#4c80f0", borderRadius: [3, 3, 0, 0] },
    },
  ],
}));
const quadStyle = computed(() => ({
  gridTemplateColumns: isReclassify.value
    ? `${columnPct.value}fr 12px ${100 - RECLASSIFY_ANNOTATION_PCT - columnPct.value}fr 12px ${RECLASSIFY_ANNOTATION_PCT}fr`
    : `${columnPct.value}fr 12px ${100 - columnPct.value}fr`,
}));
const leftPanelStyle = computed(() => ({
  gridTemplateRows: `auto ${mapPct.value}fr 10px ${100 - mapPct.value}fr`,
}));
const rightPanelStyle = computed(() =>
  isReclassify.value
    ? { gridTemplateRows: `${barPct.value}fr 10px ${100 - barPct.value}fr` }
    : undefined,
);
const barLegendSource = computed<ScLegendSource>({
  get: () => props.legendGroupBy ?? enabledLegendSources.value[0] ?? "class",
  set: (value) => emit("legend-group-change", value),
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

async function searchGlobalFilterOptions(payload: {
  field: string;
  search: string;
}): Promise<void> {
  const values = await model.loadGlobalDistinctValues(payload.field, payload.search);
  globalDistinctValues.value = { ...globalDistinctValues.value, [payload.field]: values };
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

function handleBoxSelect(region: BoxSelectionRegion): void {
  mapImmediateCrosshairDefects.value = [];
  boxSelectionQueue.enqueue({ mode: props.activeMapTab, region });
}
async function handleLegendFilterChange(payload: {
  ids: number[];
  region: { x: number; y: number; w: number; h: number };
  key?: string | number | null;
}): Promise<void> {
  const ids = payload.key != null ? await model.queryLegendSelection(payload.key) : payload.ids;
  if (payload.key != null && ids.length <= HIGHLIGHT_MAX_DEFECTS) {
    mapImmediateCrosshairDefects.value = await model.highlightDefectsForIds(ids);
  } else {
    mapImmediateCrosshairDefects.value = [];
  }
  mapImmediateCrosshairVersion.value += 1;
  await model.applyMapSelection(ids);
  emit("map-filter-change", { ...payload, ids });
}
async function handleMapSelectionChange(ids: number[]): Promise<void> {
  if (ids.length === 0) {
    mapImmediateCrosshairSeq += 1;
    mapImmediateCrosshairDefects.value = [];
    mapImmediateCrosshairVersion.value += 1;
  }
  if (ids.length === 0) await model.clearMapSelection();
  emit("map-filter-change", { ids, region: { x: 0, y: 0, w: 0, h: 0 } });
}
function handleTableSelectionChange(ids: number[]): void {
  void model.setTableSelectedDefectIds(ids);
  emit("table-selection-change", ids);
}
function handleLegendHiddenChange(payload: { source: ScLegendSource; hiddenKeys: string[] }): void {
  model.setHiddenLegendKeys(payload.hiddenKeys);
}
function reconnectPerspective(): void {
  perspective.reconnect();
}
function refreshPage(): void {
  window.location.reload();
}
async function selectBarChartGroup(defectIds: number[]): Promise<void> {
  await model.applyMapSelection(defectIds);
  emit("map-filter-change", { ids: defectIds, region: { x: 0, y: 0, w: 0, h: 0 } });
}
async function handleBarChartClick(event: ECElementEvent): Promise<void> {
  const item = barChartItems.value[typeof event.dataIndex === "number" ? event.dataIndex : -1];
  if (item) await selectBarChartGroup(item.defectIds);
}

function useBoxSelectionQueue() {
  let queuedSelections: QueuedBoxSelection[] = [];
  let drainInFlight = false;
  let drainScheduled = false;

  function clear(): void {
    queuedSelections = [];
    drainScheduled = false;
  }

  function enqueue(selection: QueuedBoxSelection): void {
    queuedSelections.push(selection);
    scheduleDrain();
  }

  function scheduleDrain(): void {
    if (drainScheduled || drainInFlight) return;
    drainScheduled = true;
    queueMicrotask(() => {
      drainScheduled = false;
      void drain();
    });
  }

  async function drain(): Promise<void> {
    if (drainInFlight) return;
    drainInFlight = true;
    try {
      while (queuedSelections.length > 0) {
        const batch = queuedSelections;
        queuedSelections = [];
        await applyBatch(batch);
      }
    } finally {
      drainInFlight = false;
      if (queuedSelections.length > 0) scheduleDrain();
    }
  }

  async function applyBatch(batch: QueuedBoxSelection[]): Promise<void> {
    const ids = new Set<number>();
    const lastRegion = batch[batch.length - 1]?.region;
    for (const selection of batch) {
      try {
        const selectedIds = await model.queryBoxSelection(selection.mode, selection.region);
        for (const id of selectedIds) ids.add(id);
      } catch (err) {
        reportPerspectiveError("box selection query failed", err);
      }
    }
    if (ids.size === 0 || !lastRegion) return;

    try {
      const nextIds = await model.appendMapSelection([...ids]);
      emit("map-filter-change", { ids: nextIds, region: lastRegion });
    } catch (err) {
      reportPerspectiveError("box selection update failed", err);
    }
  }

  return { clear, enqueue };
}

function usePerspectiveQuadData() {
  const perspective = useScPerspectiveWorkbench();
  const perspectiveReady = computed(() => perspective.dataReady.value);
  let disposed = false;
  let stopConnectWatch: (() => void) | null = null;

  function reportPerspectiveError(reason: string, err: unknown): void {
    if (disposed) return;
    console.warn("[sc-perspective] operation failed", { reason, err });
    perspective.requestReconnect(reason, err);
  }

  const perspectiveScopeKey = computed(() => {
    if (!perspectiveReady.value) return "perspective:disconnected";
    if (props.variant === "reclassify") return `perspective:dataset:${props.datasetId ?? ""}`;
    return `perspective:inspection:${props.inspectionTime ?? ""}:${props.waferKey ?? ""}`;
  });
  const galleryRandomSamplingFilter = computed<Filter[]>(() => {
    const ids = props.galleryRandomSamplingDefectIds;
    if (!ids || ids.size === 0) return [];
    return [["defect_id", "in", [...ids]] as Filter];
  });

  const model = usePerspectiveInspectionModel({
    table: perspective.table,
    inspectionTime: computed(() => props.inspectionTime),
    waferKey: computed(() => props.waferKey),
    legendGroupBy: computed(() => props.legendGroupBy),
    globalFilter: globalFilterModel,
    zoom: computed(() => props.zoom),
    activeMapMode: computed(() => props.activeMapTab),
    galleryRandomSamplingFilter,
    onRecoverableError: reportPerspectiveError,
  });
  const tableDataSource = usePerspectiveSampleTableDataSource(
    perspective.table,
    perspectiveScopeKey,
    model.tableBaseFilters,
    reportPerspectiveError,
  );

  onMounted(() => {
    stopConnectWatch = watch(
      [
        () => props.variant,
        () => props.datasetId,
        () => props.inspectionTime,
        () => props.waferKey,
        () => reticleOptionsModel.value,
      ],
      async () => {
        const opts = reticleOptionsModel.value;
        if (props.variant === "reclassify") {
          if (!props.datasetId) return perspective.disconnect();
          await perspective.connect({
            kind: "reclassify",
            datasetId: props.datasetId,
            reticleXDieCount: opts.xDieCount,
            reticleYDieCount: opts.yDieCount,
            reticleXDieShift: opts.xDieShift,
            reticleYDieShift: opts.yDieShift,
          });
          return;
        }
        if (!props.inspectionTime || props.waferKey === undefined) return perspective.disconnect();
        await perspective.connect({
          kind: "preview",
          inspectionTime: props.inspectionTime,
          waferKey: props.waferKey,
          reticleXDieCount: opts.xDieCount,
          reticleYDieCount: opts.yDieCount,
          reticleXDieShift: opts.xDieShift,
          reticleYDieShift: opts.yDieShift,
        });
      },
      { immediate: true },
    );
  });

  function dispose(): void {
    disposed = true;
    stopConnectWatch?.();
    stopConnectWatch = null;
  }

  return { perspective, perspectiveReady, model, tableDataSource, reportPerspectiveError, dispose };
}
</script>

<template>
  <perspective-viewer class="iq-hidden-perspective-viewer" aria-hidden="true" />
  <div v-if="samplesError" class="iq-state">
    <NResult status="error" :title="samplesError" description="Failed to load inspection samples"
      ><template #footer><NButton @click="emit('retry')">Retry</NButton></template></NResult
    >
  </div>
  <div
    v-else
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
    <div ref="leftPanelEl" class="iq-panel-left" :style="leftPanelStyle">
      <ScGlobalFilterBar
        :filter="globalFilterModel"
        :distinct-values="globalDistinctValues"
        @update:filter="
          globalFilterModel = $event;
          if (galleryRandomSamplingDefectIds && galleryRandomSamplingDefectIds.size > 0) {
            emit('clear-gallery-random-sampling');
          }
        "
        @search-options="searchGlobalFilterOptions"
      />
      <div class="iq-wafer">
        <ScMapPanelBinned
          :active-map-tab="activeMapTab"
          :wafer-points="activeWaferDisplay"
          :die-points="activeDieDisplay"
          :reticle-points="activeReticleDisplay"
          :legend-groups="model.legendGroups.value"
          :wafer-geometry="waferGeometry"
          :wafer-radius-nm="waferGeometry?.waferRadiusNm ?? undefined"
          :reticle-x-die-count="reticleOptionsModel.xDieCount"
          :reticle-y-die-count="reticleOptionsModel.yDieCount"
          :reticle-die-size-x="reticleDieSizeXModel"
          :reticle-die-size-y="reticleDieSizeYModel"
          :reticle-options="reticleOptionsModel"
          :legend-group-by="legendGroupBy"
          :legend-sources="enabledLegendSources"
          :zoom="zoom"
          :highlight-defects="highlightDefects"
          :immediate-crosshair-defects="mapImmediateCrosshairDefects"
          :immediate-crosshair-version="mapImmediateCrosshairVersion"
          :map-loading="model.activeMapLoading.value || !perspectiveReady"
          :map-error="model.mapError.value ?? perspective.error.value"
          :map-progress-message="perspectiveReady ? undefined : 'Loading data...'"
          :map-progress-percent="perspectiveReady ? undefined : 0"
          @update:active-map-tab="(v) => emit('update:activeMapTab', v)"
          @update:reticle-options="(v) => emit('update:reticleOptions', v)"
          @selection-change="handleMapSelectionChange"
          @legend-select="handleLegendFilterChange"
          @legend-group-change="(groupBy) => emit('legend-group-change', groupBy)"
          @legend-hidden-change="handleLegendHiddenChange"
          @zoom-in="(vp) => emit('zoom-in', vp)"
          @box-select="handleBoxSelect"
          @retry="() => emit('retry')"
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
        :data-source="tableDataSource"
        :loading="!perspectiveReady"
        :total="sampleTableTotal"
        :selected-defect-ids="tableHighlightIds"
        :filter="tableFilter"
        :sort="tableSort"
        :show-reclassify-columns="isReclassify"
        :show-global-filter-action="isReclassify"
        :global-filter-action-enabled="globalFilterActionEnabled"
        :enable-selection="true"
        :reticle-x-die-count="reticleOptionsModel.xDieCount"
        :reticle-y-die-count="reticleOptionsModel.yDieCount"
        :reticle-x-die-shift="reticleOptionsModel.xDieShift"
        :reticle-y-die-shift="reticleOptionsModel.yDieShift"
        @selection-change="handleTableSelectionChange"
        @apply-filter-as-global="(filter) => emit('table-apply-filter-as-global', filter)"
        @filter-change="(filter) => emit('table-filter-change', filter)"
        @sort-change="(sort) => emit('table-sort-change', sort)"
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
          :patch-view="model.patchBlinkView.value"
          :patch-view-version="model.patchBlinkViewVersion.value"
          :review-view="model.reviewBlinkView.value"
          :review-view-version="model.reviewBlinkViewVersion.value"
          :loading="model.blinkFetching.value"
          :dataset-id="datasetId"
          :selected-defect-ids="blinkHighlightIds"
          :inspection-time="inspectionTime"
          :wafer-key="waferKey"
          :show-prediction-badges="showPredictionBadges"
          :annotation-drafts="annotationDrafts"
          @mode-change="model.setReviewMode($event === 'review')"
          @select-samples="(ids, mods) => emit('select-samples', ids, mods)"
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
    <div v-if="perspectiveMaskVisible" class="iq-reconnect-mask">
      <div class="iq-reconnect-panel">
        <div v-if="perspective.reconnecting.value" class="iq-reconnect-spinner" />
        <NResult
          :status="perspective.reconnectFailed.value ? 'error' : 'info'"
          :title="perspectiveMaskTitle"
          :description="perspectiveMaskDescription"
        >
          <template v-if="perspective.reconnectFailed.value" #footer>
            <div class="iq-reconnect-actions">
              <NButton size="small" type="primary" @click="reconnectPerspective">Reconnect</NButton>
              <NButton size="small" quaternary @click="refreshPage">Refresh page</NButton>
            </div>
          </template>
        </NResult>
      </div>
    </div>
  </div>
</template>

<style scoped>
.iq-hidden-perspective-viewer {
  position: absolute;
  width: 0;
  height: 0;
  overflow: hidden;
  opacity: 0;
  pointer-events: none;
}
.iq-state {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  min-height: 320px;
}
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
.iq-reconnect-mask {
  position: absolute;
  inset: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 15, 26, 0.72);
  backdrop-filter: blur(2px);
  pointer-events: auto;
}
.iq-reconnect-panel {
  width: min(360px, calc(100% - 32px));
  padding: 18px 16px 14px;
  border: 1px solid var(--cv-border, rgba(255, 255, 255, 0.14));
  border-radius: 8px;
  background: var(--cv-card-bg, #1a1a2e);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.24);
}
.iq-reconnect-spinner {
  width: 24px;
  height: 24px;
  margin: 0 auto 4px;
  border: 2px solid rgba(128, 128, 128, 0.35);
  border-top-color: var(--cv-primary, #4c80f0);
  border-radius: 50%;
  animation: iq-reconnect-spin 0.8s linear infinite;
}
.iq-reconnect-actions {
  display: flex;
  justify-content: center;
  gap: 8px;
}
@keyframes iq-reconnect-spin {
  to {
    transform: rotate(360deg);
  }
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
