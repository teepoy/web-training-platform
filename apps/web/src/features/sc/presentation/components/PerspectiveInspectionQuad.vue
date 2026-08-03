<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from "vue";
import { NButton, NResult, NSelect } from "naive-ui";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsOption } from "echarts";
import type { ECElementEvent } from "echarts/core";
import type { ScMapLassoSelection } from "@platform/sc-map-element";
import ScMapPanelBinned from "@/features/sc/presentation/components/ScMapPanelBinned.vue";
import ScGlobalFilterBar from "@/features/sc/presentation/components/ScGlobalFilterBar.vue";
import ScSampleTableVxe from "@/features/sc/presentation/components/ScSampleTableVxe.vue";
import ScBlinkVirtualTable from "@/features/sc/presentation/components/ScBlinkVirtualTable.vue";
import type { ScSampleTableFilter, ScSampleTableSort } from "@/features/sc/domain/sampleTable";
import type {
  ScLegendSource,
  ScMapRegion,
  ScMapSelectionChange,
} from "@/features/sc/domain/workbenchInteraction";
import type { ReticleMapOptions } from "@/features/sc/application/reticleMapOptions";
import type { HighlightDefect } from "@/features/sc/presentation/components/types";
import { perspectiveReticleExpressions } from "@/features/sc/presentation/composables/perspectiveReticleExpressions";
import { usePerspectiveInspectionQuadData } from "@/features/sc/presentation/composables/usePerspectiveInspectionQuadData";

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

const props = defineProps<{
  variant?: "preview" | "reclassify";
  datasetId?: string;
  inspectionTime: string;
  waferKey: number;
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
  reticleDieSizeX: number;
  reticleDieSizeY: number;
  reticleOptions: ReticleMapOptions;
  zoom?: { x: number; y: number; w: number; h: number } | null;
  selectedGalleryDefectIds?: Array<number | string>;
  globalFilter?: ScSampleTableFilter;
  tableFilter?: ScSampleTableFilter;
  tableSort?: ScSampleTableSort | null;
  galleryRandomSamplingDefectIds?: Set<string>;
}>();

const emit = defineEmits<{
  (e: "update:activeMapTab", v: "wafer" | "die" | "reticle"): void;
  (e: "update:reticleOptions", v: ReticleMapOptions): void;
  (e: "zoom-in", vp: { x: number; y: number; w: number; h: number } | null): void;
  (e: "map-selection-change", change: ScMapSelectionChange): void;
  (e: "update:tableFilter", filter: ScSampleTableFilter): void;
  (e: "update:global-filter", filter: ScSampleTableFilter): void;
  (e: "update:tableSort", sort: ScSampleTableSort | null): void;
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
const reticleOptionsModel = computed(() => props.reticleOptions);
const reticleExpressionsModel = computed(() =>
  perspectiveReticleExpressions(reticleOptionsModel.value, {
    dieSizeX: props.reticleDieSizeX,
    dieSizeY: props.reticleDieSizeY,
  }),
);

const { perspective, perspectiveReady, model, reportPerspectiveError } =
  usePerspectiveInspectionQuadData({
    variant: computed(() => props.variant),
    datasetId: computed(() => props.datasetId),
    inspectionTime: computed(() => props.inspectionTime),
    waferKey: computed(() => props.waferKey),
    legendGroupBy: computed(() => props.legendGroupBy),
    globalFilter: globalFilterModel,
    tableFilter: computed(() => props.tableFilter),
    tableSort: computed(() => props.tableSort),
    reticleExpressions: reticleExpressionsModel,
    galleryRandomSamplingDefectIds: computed(() => props.galleryRandomSamplingDefectIds),
  });

async function queryGlobalFilterCount(): Promise<number> {
  return model.queryGlobalFilterCount();
}

async function queryRandomGlobalFilteredDefectIds(count: number): Promise<number[]> {
  return model.queryRandomGlobalFilteredDefectIds(count);
}

defineExpose({ queryGlobalFilterCount, queryRandomGlobalFilteredDefectIds });

const tableHighlightIds = computed(
  () => new Set((model.tableSelectedDefectIds.value ?? []).map(Number).filter(Number.isFinite)),
);
const blinkHighlightIds = computed(
  () => new Set((props.selectedGalleryDefectIds ?? []).map(String)),
);
const perspectiveMaskVisible = computed(
  () => perspective.reconnecting.value || perspective.reconnectFailed.value,
);
const perspectiveMaskTitle = computed(() =>
  perspective.reconnectFailed.value ? "Data connection lost" : "Restoring connection...",
);
const perspectiveMaskDescription = computed(() => {
  if (perspective.reconnectFailed.value) {
    return "Automatic reconnect failed. Try reconnecting manually, or refresh the page.";
  }
  const attempt = perspective.reconnectAttempt.value;
  const maxAttempts = perspective.reconnectMaxAttempts;
  return attempt > 0
    ? `Restoring the data connection (${attempt}/${maxAttempts})`
    : "Restoring the data connection";
});
const userFacingMapError = computed(() => {
  if (model.mapError.value) return "Map data could not be loaded. Try again.";
  if (perspective.error.value) return "The data connection was interrupted. Try reconnecting.";
  return null;
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
const mapSelectionQueue = useMapSelectionQueue();

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
  if (_highlightTimer !== null) clearTimeout(_highlightTimer);
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

watch(
  () => props.legendGroupBy,
  () => {
    selectedBarChartKey.value = null;
  },
);

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

function handleBoxSelect(region: ScMapRegion): void {
  selectedBarChartKey.value = null;
  mapImmediateCrosshairDefects.value = [];
  mapSelectionQueue.append({ kind: "box", mode: props.activeMapTab, region });
}
function handleLassoSelect(selection: ScMapLassoSelection): void {
  selectedBarChartKey.value = null;
  mapImmediateCrosshairDefects.value = [];
  mapSelectionQueue.append({
    kind: "lasso",
    mode: props.activeMapTab,
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
  mapImmediateCrosshairSeq += 1;
  mapImmediateCrosshairDefects.value = [];
  mapImmediateCrosshairVersion.value += 1;
  mapSelectionQueue.clear();
}
function handleTableSelectionChange(ids: number[]): void {
  void model.setTableSelectedDefectIds(ids);
  emit("table-selection-change", ids);
}
function handleTableSortChange(sort: { field: string; direction: "asc" | "desc" | null }): void {
  emit(
    "update:tableSort",
    sort.direction ? { field: sort.field, direction: sort.direction } : null,
  );
}
function reconnectPerspective(): void {
  perspective.reconnect();
}
function refreshPage(): void {
  window.location.reload();
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
        reportPerspectiveError(failureReason, error);
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
      const ids = await model.appendMapSelection(selectedIds);
      if (version !== replacementVersion) return;
      emit("map-selection-change", {
        source: selection.kind,
        mode: "append",
        ids,
        region: selection.region,
      });
    }, `${selection.kind} selection failed`);
  }

  function replace(source: "legend" | "bar-chart", key: string | number | null): void {
    const version = ++replacementVersion;
    // Replacement actions supersede slow area queries immediately. Model
    // mutations remain serialized by usePerspectiveInspectionModel.
    queue = Promise.resolve();
    enqueue(async () => {
      if (version !== replacementVersion) return;
      const ids = key === null ? [] : await model.queryLegendSelection(key);
      if (version !== replacementVersion) return;
      if (key !== null && ids.length <= HIGHLIGHT_MAX_DEFECTS) {
        mapImmediateCrosshairDefects.value = await model.highlightDefectsForIds(ids);
      } else {
        mapImmediateCrosshairDefects.value = [];
      }
      if (version !== replacementVersion) return;
      mapImmediateCrosshairVersion.value += 1;
      await model.applyMapSelection(ids);
      if (version !== replacementVersion) return;
      emit("map-selection-change", {
        source,
        mode: key === null ? "clear" : "replace",
        ids,
        groupKey: key,
      });
    }, `${source} selection failed`);
  }

  function clear(): void {
    const version = ++replacementVersion;
    queue = Promise.resolve();
    enqueue(async () => {
      if (version !== replacementVersion) return;
      await model.clearMapSelection();
      if (version !== replacementVersion) return;
      emit("map-selection-change", {
        source: "clear",
        mode: "clear",
        ids: [],
      });
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
          :arrow-data="model.mapArrowData.value"
          :map-legend-column="model.mapLegendColumn.value"
          :legend-groups="model.legendGroups.value"
          :wafer-geometry="waferGeometry"
          :wafer-radius-nm="waferGeometry?.waferRadiusNm ?? undefined"
          :reticle-die-size-x="reticleDieSizeX"
          :reticle-die-size-y="reticleDieSizeY"
          :reticle-options="reticleOptionsModel"
          :legend-group-by="legendGroupBy"
          :legend-sources="enabledLegendSources"
          :zoom="zoom"
          :highlight-defects="highlightDefects"
          :immediate-crosshair-defects="mapImmediateCrosshairDefects"
          :immediate-crosshair-version="mapImmediateCrosshairVersion"
          :map-loading="model.activeMapLoading.value || !perspectiveReady"
          :map-error="userFacingMapError"
          :map-progress-message="
            perspectiveReady ? model.mapProgressMessage.value : 'Connecting to data service...'
          "
          :map-progress-percent="perspectiveReady ? model.mapProgressPercent.value : 0"
          @update:active-map-tab="(v) => emit('update:activeMapTab', v)"
          @update:reticle-options="(v) => emit('update:reticleOptions', v)"
          @clear-selection="handleClearMapSelection"
          @legend-select="handleLegendSelection"
          @legend-group-change="(groupBy) => emit('legend-group-change', groupBy)"
          @zoom-in="(vp) => emit('zoom-in', vp)"
          @box-select="handleBoxSelect"
          @lasso-select="handleLassoSelect"
          @retry="reconnectPerspective"
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
      <ScSampleTableVxe
        v-if="perspective.table.value"
        :perspective-table="perspective.table.value"
        :base-view-config="model.sampleTableBaseViewConfig.value"
        :loading="!perspectiveReady"
        :selected-defect-ids="tableHighlightIds"
        :ignored-perspective-update-port-ids="model.sampleTableIgnoredUpdatePortIds.value"
        :filter="tableFilter"
        :sort="tableSort"
        :show-reclassify-columns="isReclassify"
        :enable-selection="true"
        @selection-change="handleTableSelectionChange"
        @filter-change="(filter) => emit('update:tableFilter', filter)"
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
          :patch-view-snapshot="model.patchGalleryViewSnapshot.value"
          :review-view-snapshot="model.reviewGalleryViewSnapshot.value"
          :loading="model.galleryLoading.value"
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
