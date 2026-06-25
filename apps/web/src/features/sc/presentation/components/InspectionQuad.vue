<script setup lang="ts">
import { computed, ref } from "vue";
import { NButton, NResult, NSelect, NText } from "naive-ui";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsOption } from "echarts";
import type { ECElementEvent } from "echarts/core";
import ScMapPanel from "@/features/sc/presentation/components/ScMapPanel.vue";
import ScSampleTable from "@/features/sc/presentation/components/ScSampleTable.vue";
import ScPreviewBlinkVirtualTable from "@/features/sc/presentation/components/ScPreviewBlinkVirtualTable.vue";
import type { DefectList, ScSampleItem } from "@/features/sc/generated/proto/sc/v1/sample_pb";
import type { InspectionSummaryItem } from "@/features/sc/domain/models";
import type { ScSampleTableFilter, ScSampleTableSort } from "@/features/sc/domain/sampleTable";
import type { ScLegendSource } from "@/features/sc/domain/workbenchInteraction";
import type { ReticleMapOptions } from "@/features/sc/application/reticleMapOptions";
import type { HighlightDefect } from "@/features/sc/presentation/components/types";
import {
  createDatasetSampleTableDataSource,
  createInspectionSampleTableDataSource,
} from "@/features/sc/api/sampleTableDataSource";
import {
  fetchScDatasetBoxFilter,
  fetchScInspectionBoxFilter,
  type ScBoxRegion,
  type ScMapMode,
} from "@/features/sc/api/boxFilter";

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

// ── Props / emits ────────────────────────────────
const props = defineProps<{
  variant?: "preview" | "reclassify";
  datasetId?: string;
  samples: ScSampleItem[];
  samplesTotal: number;
  samplesLoading: boolean;
  samplesError: string | null;
  inspectionTime?: string;
  waferKey?: number;
  reviewSamples?: ScSampleItem[];
  reviewLoading?: boolean;
  reviewError?: string | null;
  mapLoading?: boolean;
  mapError?: string | null;
  mapStreamMessage?: string;
  mapProgressPercent?: number;
  inspectionItem?: InspectionSummaryItem;
  activeMapTab: "wafer" | "die" | "reticle";
  /** Wafer geometry (center, origin, die sizes) for die grid rendering */
  waferGeometry?: {
    waferRadiusNm: number;
    centerX: number;
    centerY: number;
    originX: number;
    originY: number;
    dieSizeX: number;
    dieSizeY: number;
  } | null;
  /** Pre-computed wafer display flat array [x, y, defect_id, class_num, rough_bin, has_review, ...] — 6 ints per point */
  waferDisplay?: number[];
  /** Pre-computed die display flat array [dieX, dieY, defect_id, class_num, rough_bin, has_review, ...] — 6 ints per point */
  dieDisplay?: number[];
  /** Pre-computed reticle display flat array [reticleX, reticleY, id, ...] from backend */
  reticleDisplay?: number[];
  /** Full (unsampled) arrays for selection only — used when total >= 50k */
  unzoomedWaferDisplay?: number[];
  unzoomedDieDisplay?: number[];
  unzoomedReticleDisplay?: number[];
  legendGroups?: Record<string, DefectList> | null;
  legendGroupBy?: ScLegendSource | null;
  legendSources?: ScLegendSource[];
  reticleXDieCount?: number;
  reticleYDieCount?: number;
  reticleDieSizeX?: number;
  reticleDieSizeY?: number;
  reticleOptions?: ReticleMapOptions;
  zoom?: { x: number; y: number; w: number; h: number } | null;
  selectedDefectIds?: Array<number | string>;
  tableFilter?: ScSampleTableFilter;
  mapSampleFilter?: ScSampleTableFilter;
  globalFilterActionEnabled?: boolean;
  tableSort?: ScSampleTableSort | null;
}>();

const emit = defineEmits<{
  (e: "update:activeMapTab", v: "wafer" | "die" | "reticle"): void;
  (e: "update:reticleOptions", v: ReticleMapOptions): void;
  (e: "zoom-in", vp: { x: number; y: number; w: number; h: number } | null): void;
  (
    e: "select-points",
    payload: {
      ids: number[];
      region: { x: number; y: number; w: number; h: number };
    },
  ): void;
  (e: "table-filter-change", filter: ScSampleTableFilter): void;
  (e: "table-apply-filter-as-global", filter: ScSampleTableFilter): void;
  (e: "table-sort-change", sort: { field: string; direction: "asc" | "desc" | null }): void;
  (e: "table-selection-change", ids: number[]): void;
  (e: "table-apply-selection", ids: number[]): void;
  (e: "legend-group-change", groupBy: string | null): void;
  (e: "legend-hidden-change", payload: { source: ScLegendSource; hiddenKeys: string[] }): void;
  (e: "retry"): void;
}>();

const DEFAULT_COLUMN_PCT = 35;
const MIN_COLUMN_PCT = 20;
const MAX_COLUMN_PCT = 80;
const RECLASSIFY_ANNOTATION_PCT = 15;
const MIN_CENTER_PCT = 15;
const DEFAULT_MAP_PCT = 55;
const MIN_MAP_PCT = 25;
const MAX_MAP_PCT = 75;
const DEFAULT_BAR_PCT = 60;
const MIN_BAR_PCT = 15;
const MAX_BAR_PCT = 85;

const quadEl = ref<HTMLElement | null>(null);
const leftPanelEl = ref<HTMLElement | null>(null);
const rightPanelEl = ref<HTMLElement | null>(null);
const columnPct = ref(DEFAULT_COLUMN_PCT);
const mapPct = ref(DEFAULT_MAP_PCT);
const barPct = ref(DEFAULT_BAR_PCT);
const isColumnResizing = ref(false);
const isRowResizing = ref(false);
const isBarResizing = ref(false);

const quadStyle = computed(() => ({
  gridTemplateColumns:
    props.variant === "reclassify"
      ? `${columnPct.value}fr 12px ${100 - RECLASSIFY_ANNOTATION_PCT - columnPct.value}fr 12px ${RECLASSIFY_ANNOTATION_PCT}fr`
      : `${columnPct.value}fr 12px ${100 - columnPct.value}fr`,
}));

const leftPanelStyle = computed(() => ({
  gridTemplateRows: `${mapPct.value}fr 10px ${100 - mapPct.value}fr`,
}));

const rightPanelStyle = computed(() => {
  if (!isReclassify.value) return undefined;
  return {
    gridTemplateRows: `${barPct.value}fr 10px ${100 - barPct.value}fr`,
  };
});

const isReclassify = computed(() => props.variant === "reclassify");
const enabledLegendSources = computed<ScLegendSource[]>(
  () =>
    props.legendSources ??
    (isReclassify.value ? ["class", "bin", "annotation", "prediction"] : ["class", "bin"]),
);

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function onColumnResizeStart(e: PointerEvent): void {
  e.preventDefault();
  if (e.currentTarget instanceof Element) {
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  isColumnResizing.value = true;
}

function onColumnResizeMove(e: PointerEvent): void {
  if (!isColumnResizing.value || !quadEl.value) return;
  const rect = quadEl.value.getBoundingClientRect();
  if (rect.width <= 0) return;
  const nextPct = ((e.clientX - rect.left) / rect.width) * 100;
  const maxPct = isReclassify.value
    ? 100 - RECLASSIFY_ANNOTATION_PCT - MIN_CENTER_PCT
    : MAX_COLUMN_PCT;
  columnPct.value = clamp(nextPct, MIN_COLUMN_PCT, maxPct);
}

function onColumnResizeEnd(e: PointerEvent): void {
  if (!isColumnResizing.value) return;
  isColumnResizing.value = false;
  if (e.currentTarget instanceof Element) {
    e.currentTarget.releasePointerCapture(e.pointerId);
  }
}

function onRowResizeStart(e: PointerEvent): void {
  e.preventDefault();
  if (e.currentTarget instanceof Element) {
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  isRowResizing.value = true;
}

function onRowResizeMove(e: PointerEvent): void {
  if (!isRowResizing.value || !leftPanelEl.value) return;
  const rect = leftPanelEl.value.getBoundingClientRect();
  if (rect.height <= 0) return;
  const nextPct = ((e.clientY - rect.top) / rect.height) * 100;
  mapPct.value = clamp(nextPct, MIN_MAP_PCT, MAX_MAP_PCT);
}

function onRowResizeEnd(e: PointerEvent): void {
  if (!isRowResizing.value) return;
  isRowResizing.value = false;
  if (e.currentTarget instanceof Element) {
    e.currentTarget.releasePointerCapture(e.pointerId);
  }
}

function onBarResizeStart(e: PointerEvent): void {
  e.preventDefault();
  if (e.currentTarget instanceof Element) {
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  isBarResizing.value = true;
}

function onBarResizeMove(e: PointerEvent): void {
  if (!isBarResizing.value || !rightPanelEl.value) return;
  const rect = rightPanelEl.value.getBoundingClientRect();
  if (rect.height <= 0) return;
  const nextPct = ((e.clientY - rect.top) / rect.height) * 100;
  barPct.value = clamp(nextPct, MIN_BAR_PCT, MAX_BAR_PCT);
}

function onBarResizeEnd(e: PointerEvent): void {
  if (!isBarResizing.value) return;
  isBarResizing.value = false;
  if (e.currentTarget instanceof Element) {
    e.currentTarget.releasePointerCapture(e.pointerId);
  }
}

// ── Selection state ──────────────────────────────
const mapSelectionIds = ref<number[]>([]);

const filteredSamples = computed<ScSampleItem[]>(() => {
  if (mapSelectionIds.value.length === 0) return props.samples;
  const filter = new Set(mapSelectionIds.value);
  return props.samples.filter((s) => filter.has(s.defectId));
});

const blinkSamples = computed<ScSampleItem[]>(() => {
  const selectedIds = props.selectedDefectIds ?? [];
  if (selectedIds.length > 0) {
    const filter = new Set(selectedIds);
    return props.samples.filter((s) => filter.has(s.defectId));
  }
  return filteredSamples.value;
});

const filteredDefectIds = computed<string[] | undefined>(() =>
  mapSelectionIds.value.length > 0 ? mapSelectionIds.value.map(String) : undefined,
);

const filteredReviewSamples = computed<ScSampleItem[]>(() => {
  const samples = props.reviewSamples ?? [];
  const selectedIds = props.selectedDefectIds ?? [];
  const sourceIds = selectedIds.length > 0 ? selectedIds : mapSelectionIds.value;
  if (sourceIds.length === 0) return samples;
  const filter = new Set(sourceIds);
  return samples.filter((s) => filter.has(s.defectId));
});

const filteredTotal = computed<number>(() => {
  if (mapSelectionIds.value.length === 0) return props.samplesTotal;
  return filteredSamples.value.length;
});

// Legend-only selection IDs for map highlighting (map wrapper manages box-selection internally)
const legendSelectedIds = computed<ReadonlySet<number>>(() => new Set());

// ── queryBoxSelection: curried API call for map wrapper box-selection ──
async function queryBoxSelection(mode: ScMapMode, region: ScBoxRegion): Promise<number[]> {
  if (props.variant === "reclassify") {
    const datasetId = props.datasetId;
    if (!datasetId) {
      throw new Error("datasetId is required for reclassify map box selection");
    }
    const result = await fetchScDatasetBoxFilter(
      datasetId,
      mode,
      region,
      reticleOptionsModel.value,
      props.mapSampleFilter,
    );
    return result.defect_ids.map(Number);
  }

  const inspectionTime = props.inspectionTime;
  const waferKey = props.waferKey;
  if (!inspectionTime || waferKey === undefined) {
    throw new Error("inspection identity is required for preview map box selection");
  }
  const result = await fetchScInspectionBoxFilter(
    inspectionTime,
    waferKey,
    mode,
    region,
    reticleOptionsModel.value,
    props.mapSampleFilter,
  );
  return result.defect_ids.map(Number);
}

const sampleTableDataSource = computed(() => {
  if (props.variant === "reclassify") {
    return props.datasetId ? createDatasetSampleTableDataSource(props.datasetId) : undefined;
  }
  return props.inspectionTime && props.waferKey !== undefined
    ? createInspectionSampleTableDataSource(props.inspectionTime, props.waferKey)
    : undefined;
});

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

// ── Unzoomed-points fallback (empty array is not nullish, so `??` won't work) ──
const effectiveWaferPoints = computed<number[] | undefined>(() => {
  const f = props.unzoomedWaferDisplay;
  return f && f.length > 0 ? f : props.waferDisplay;
});

const effectiveDiePoints = computed<number[] | undefined>(() => {
  const f = props.unzoomedDieDisplay;
  return f && f.length > 0 ? f : props.dieDisplay;
});

const effectiveReticlePoints = computed<number[] | undefined>(() => {
  const f = props.unzoomedReticleDisplay;
  return f && f.length > 0 ? f : props.reticleDisplay;
});

const sampleTableRef = ref<InstanceType<typeof ScSampleTable> | null>(null);

const selectedNumericIds = computed(
  () => new Set((props.selectedDefectIds ?? []).map(Number).filter(Number.isFinite)),
);

const selectedStringIds = computed(() => new Set((props.selectedDefectIds ?? []).map(String)));

const highlightDefects = computed<HighlightDefect[]>(() => {
  const ids = props.selectedDefectIds;
  if (!ids || ids.length === 0) return [];

  const result: HighlightDefect[] = [];
  for (const id of ids) {
    const defectId = Number(id);
    if (!Number.isFinite(defectId)) continue;
    const coords = sampleTableRef.value?.getDefectCoords?.(defectId);
    if (!coords) continue;
    result.push({
      defectId,
      waferX: coords.waferX,
      waferY: coords.waferY,
      dieX: coords.dieX,
      dieY: coords.dieY,
      reticleX: coords.reticleX,
      reticleY: coords.reticleY,
    });
  }
  return result;
});

const barChartItems = computed(() => {
  const groups = props.legendGroups ?? {};
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
  grid: { left: 80, right: 32, top: 8, bottom: 18 },
  tooltip: {
    trigger: "axis",
    axisPointer: { type: "shadow" },
  },
  xAxis: {
    type: "value",
    axisLabel: { color: "rgba(120, 120, 120, 0.8)", fontSize: 10 },
    splitLine: { lineStyle: { color: "rgba(128, 128, 128, 0.15)" } },
  },
  yAxis: {
    type: "category",
    inverse: true,
    data: barChartItems.value.map((item) => item.key),
    axisLabel: { color: "rgba(120, 120, 120, 0.9)", fontSize: 10 },
    axisTick: { show: false },
    axisLine: { show: false },
  },
  series: [
    {
      type: "bar",
      data: barChartItems.value.map((item) => item.count),
      barMaxWidth: 12,
      itemStyle: {
        color: "#4c80f0",
        borderRadius: [0, 3, 3, 0],
      },
    },
  ],
}));

function handleMapSelectionChange(ids: number[]): void {
  mapSelectionIds.value = ids;
  emit("select-points", {
    ids,
    region: { x: 0, y: 0, w: 0, h: 0 },
  });
}

function handleMapSelectPoints(payload: {
  ids: number[];
  region: { x: number; y: number; w: number; h: number };
}): void {
  mapSelectionIds.value = payload.ids;
  emit("select-points", payload);
}

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
  };
  return enabledLegendSources.value.map((source) => ({
    label: labels[source],
    value: source,
  }));
});

function selectBarChartGroup(defectIds: number[]): void {
  mapSelectionIds.value = defectIds;
  emit("select-points", {
    ids: defectIds,
    region: { x: 0, y: 0, w: 0, h: 0 },
  });
}

function handleBarChartClick(event: ECElementEvent): void {
  const index = typeof event.dataIndex === "number" ? event.dataIndex : -1;
  const item = barChartItems.value[index];
  if (item) selectBarChartGroup(item.defectIds);
}
</script>

<template>
  <!-- Error state -->
  <div v-if="samplesError" class="iq-state">
    <NResult status="error" :title="samplesError" description="Failed to load inspection samples">
      <template #footer>
        <NButton @click="emit('retry')">Retry</NButton>
      </template>
    </NResult>
  </div>

  <!-- Quad layout -->
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
    <!-- Left column: Wafer/Die Map (top) + Sample Data (bottom) -->
    <div ref="leftPanelEl" class="iq-panel-left" :style="leftPanelStyle">
      <div class="iq-wafer">
        <ScMapPanel
          :active-map-tab="activeMapTab"
          :wafer-points="waferDisplay"
          :wafer-full-points="effectiveWaferPoints"
          :die-points="dieDisplay"
          :die-full-points="effectiveDiePoints"
          :reticle-points="reticleDisplay"
          :reticle-full-points="effectiveReticlePoints"
          :legend-groups="legendGroups"
          :wafer-geometry="waferGeometry"
          :wafer-radius-nm="waferGeometry?.waferRadiusNm ?? undefined"
          :reticle-x-die-count="reticleOptionsModel.xDieCount"
          :reticle-y-die-count="reticleOptionsModel.yDieCount"
          :reticle-die-size-x="reticleDieSizeXModel"
          :reticle-die-size-y="reticleDieSizeYModel"
          :reticle-options="reticleOptionsModel"
          :legend-group-by="legendGroupBy"
          :legend-sources="enabledLegendSources"
          :selected-ids="legendSelectedIds"
          :highlight-defects="highlightDefects"
          :query-box-selection="queryBoxSelection"
          :zoom="zoom"
          :map-loading="mapLoading"
          :map-error="mapError"
          :map-progress-message="mapStreamMessage"
          :map-progress-percent="mapProgressPercent"
          @update:active-map-tab="(v) => emit('update:activeMapTab', v)"
          @update:reticle-options="(v) => emit('update:reticleOptions', v)"
          @selection-change="handleMapSelectionChange"
          @select-points="handleMapSelectPoints"
          @legend-group-change="(groupBy) => emit('legend-group-change', groupBy)"
          @legend-hidden-change="(payload) => emit('legend-hidden-change', payload)"
          @zoom-in="(vp) => emit('zoom-in', vp)"
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
        ref="sampleTableRef"
        :data-source="sampleTableDataSource"
        :defect-ids="filteredDefectIds"
        :loading="false"
        :total="filteredTotal"
        :selected-defect-ids="selectedNumericIds"
        :filter="tableFilter"
        :sort="tableSort"
        :show-reclassify-columns="isReclassify"
        :show-global-filter-action="isReclassify"
        :global-filter-action-enabled="globalFilterActionEnabled"
        :enable-selection="isReclassify"
        :reticle-x-die-count="reticleOptionsModel.xDieCount"
        :reticle-y-die-count="reticleOptionsModel.yDieCount"
        :reticle-x-die-shift="reticleOptionsModel.xDieShift"
        :reticle-y-die-shift="reticleOptionsModel.yDieShift"
        @selection-change="(ids) => emit('table-selection-change', ids)"
        @apply-selection="(ids) => emit('table-apply-selection', ids)"
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

    <!-- Right column: Blink Table -->
    <div
      ref="rightPanelEl"
      class="iq-panel-right"
      :class="{ 'iq-panel-right--split': isReclassify }"
      :style="rightPanelStyle"
    >
      <div class="iq-blink-pane">
        <slot name="blink">
          <ScPreviewBlinkVirtualTable
            :samples="blinkSamples"
            :review-samples="filteredReviewSamples"
            :review-loading="reviewLoading"
            :review-error="reviewError"
            :blink-interval-ms="800"
            :initial-blink-enabled="true"
            :selected-defect-ids="selectedStringIds"
            :inspection-time="inspectionTime"
          />
        </slot>
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

    <template v-if="isReclassify">
      <div class="iq-splitter iq-splitter--column" role="separator" aria-orientation="vertical" />
      <div class="iq-panel-annotation">
        <slot name="annotation" />
      </div>
    </template>
  </div>
</template>

<style scoped>
/* ── State ──────────────────────────────────────────── */
.iq-state {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  min-height: 320px;
}

/* ── 2-column grid ──────────────────────────────────── */
.iq-quad {
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

.iq-quad--column-resizing *,
.iq-quad--row-resizing *,
.iq-quad--bar-resizing * {
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

.iq-panel-right > *,
.iq-blink-pane > * {
  flex: 1;
  min-height: 0;
}

.iq-panel-right--split {
  display: grid;
  gap: 0;
}

.iq-blink-pane {
  display: flex;
  min-height: 0;
  overflow: hidden;
  background: var(--cv-card-bg, #1a1a2e);
  border: 1px solid var(--cv-border, rgba(255, 255, 255, 0.1));
  border-radius: 8px;
  padding: 8px 10px;
}

.iq-bar-pane {
  grid-row: 3;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--cv-card-bg, #1a1a2e);
  border: 1px solid var(--cv-border, rgba(255, 255, 255, 0.1));
  border-radius: 8px;
  padding: 8px 10px;
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

/* ── Tabs ───────────────────────────────────────────── */
.iq-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.iq-tabs :deep(.n-tabs-pane-wrapper) {
  flex: 1;
  min-height: 0;
}

.iq-tabs :deep(.n-tab-pane),
.iq-tabs :deep(.n-spin-container),
.iq-tabs :deep(.n-spin-content) {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* ── Wafer ──────────────────────────────────────────── */
.iq-wafer {
  flex: 1 1 0;
  min-height: 0;
  width: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--cv-card-bg, #1a1a2e);
  border: 1px solid var(--cv-border, rgba(255, 255, 255, 0.1));
  border-radius: 8px;
  padding: 8px 10px;
}

.iq-map-error {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  min-height: 180px;
}

.iq-reticle-options {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 6px 4px 2px;
  font-size: 11px;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.55));
}
</style>
