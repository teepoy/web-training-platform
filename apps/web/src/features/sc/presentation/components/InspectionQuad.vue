<script setup lang="ts">
import { computed, ref } from "vue";
import {
  NButton,
  NResult,
  NText,
} from "naive-ui";
import ScMapPanel from "@/features/sc/presentation/components/ScMapPanel.vue";
import ScSampleTable from "@/features/sc/presentation/components/ScSampleTable.vue";
import ScPreviewBlinkVirtualTable from "@/features/sc/presentation/components/ScPreviewBlinkVirtualTable.vue";
import type {
  ClassList,
  ScSampleItem,
} from "@/features/sc/generated/proto/sc/v1/sample_pb";
import type { InspectionSummaryItem } from "@/features/sc/domain/models";
import type { ReticleMapOptions } from "@/features/sc/application/reticleMapOptions";
import {
  fetchScInspectionBoxFilter,
  type ScBoxRegion,
  type ScMapMode,
} from "@/features/sc/api/boxFilter";

// ── Props / emits ────────────────────────────────
const props = defineProps<{
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
  fullWaferDisplay?: number[];
  fullDieDisplay?: number[];
  fullReticleDisplay?: number[];
  classList?: ClassList | null;
  reticleXDieCount?: number;
  reticleYDieCount?: number;
  reticleDieSizeX?: number;
  reticleDieSizeY?: number;
  reticleOptions?: ReticleMapOptions;
  zoom?: { x: number; y: number; w: number; h: number } | null;
}>();

const emit = defineEmits<{
  (e: "update:activeMapTab", v: "wafer" | "die" | "reticle"): void;
  (e: "update:reticleOptions", v: ReticleMapOptions): void;
  (e: "zoom-in", vp: { x: number; y: number; w: number; h: number } | null): void;
  (e: "select-points", payload: { ids: number[]; region: { x: number; y: number; w: number; h: number } }): void;
  (e: "retry"): void;
}>();

const DEFAULT_COLUMN_PCT = 55;
const MIN_COLUMN_PCT = 20;
const MAX_COLUMN_PCT = 80;
const DEFAULT_MAP_PCT = 55;
const MIN_MAP_PCT = 25;
const MAX_MAP_PCT = 75;

const quadEl = ref<HTMLElement | null>(null);
const leftPanelEl = ref<HTMLElement | null>(null);
const columnPct = ref(DEFAULT_COLUMN_PCT);
const mapPct = ref(DEFAULT_MAP_PCT);
const isColumnResizing = ref(false);
const isRowResizing = ref(false);

const quadStyle = computed(() => ({
  gridTemplateColumns: `${columnPct.value}fr 12px ${100 - columnPct.value}fr`,
}));

const leftPanelStyle = computed(() => ({
  gridTemplateRows: `${mapPct.value}fr 10px ${100 - mapPct.value}fr`,
}));

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
  columnPct.value = clamp(nextPct, MIN_COLUMN_PCT, MAX_COLUMN_PCT);
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

// ── Selection state ──────────────────────────────
const selectedDefectIds = ref<Set<string>>(new Set());
const selectionVersion = ref(0);

function onSelectPoints(payload: { ids: (string | number)[]; region: { x: number; y: number; w: number; h: number } }): void {
  if (payload.ids.length === 0) {
    selectedDefectIds.value = new Set();
  } else {
    for (const id of payload.ids) selectedDefectIds.value.add(String(id));
  }
  selectionVersion.value++;
  emit("select-points", { ids: payload.ids.map(Number), region: payload.region });
}

async function onFilterRegion(payload: {
  mode: ScMapMode;
  region: ScBoxRegion;
}): Promise<void> {
  if (!props.inspectionTime || props.waferKey === undefined) return;
  const result = await fetchScInspectionBoxFilter(
    props.inspectionTime,
    props.waferKey,
    payload.mode,
    payload.region,
    reticleOptionsModel.value,
  );
  onSelectPoints({
    ids: result.defect_ids,
    region: payload.region,
  });
}

function clearSelection(): void {
  selectedDefectIds.value = new Set();
  selectionVersion.value++;
}

const filteredSamples = computed<ScSampleItem[]>(() => {
  if (selectedDefectIds.value.size === 0) return props.samples;
  const filter = selectedDefectIds.value;
  return props.samples.filter((s) => filter.has(String(s.defectId)));
});

const filteredDefectIds = computed<string[]>(() =>
  filteredSamples.value.map((sample) => String(sample.defectId)),
);

const filteredReviewSamples = computed<ScSampleItem[]>(() => {
  const samples = props.reviewSamples ?? [];
  if (selectedDefectIds.value.size === 0) return samples;
  const filter = selectedDefectIds.value;
  return samples.filter((s) => filter.has(String(s.defectId)));
});

const filteredTotal = computed<number>(() => {
  if (selectedDefectIds.value.size === 0) return props.samplesTotal;
  return filteredSamples.value.length;
});
const mapSelectedDefectIds = computed(
  () =>
    new Set(
      [...selectedDefectIds.value].map(Number).filter(Number.isFinite),
    ),
);

const reticleOptionsModel = computed<ReticleMapOptions>(() => ({
  xDieCount: props.reticleOptions?.xDieCount ?? props.reticleXDieCount ?? 10,
  yDieCount: props.reticleOptions?.yDieCount ?? props.reticleYDieCount ?? 10,
  xDieShift: props.reticleOptions?.xDieShift ?? 0,
  yDieShift: props.reticleOptions?.yDieShift ?? 0,
}));

const reticleDieSizeXModel = computed(() => props.reticleDieSizeX ?? props.inspectionItem?.die_size_x ?? 100000);
const reticleDieSizeYModel = computed(() => props.reticleDieSizeY ?? props.inspectionItem?.die_size_y ?? 100000);

// ── Full-points fallback (empty array is not nullish, so `??` won't work) ──
const effectiveWaferFullPoints = computed<number[] | undefined>(() => {
  const f = props.fullWaferDisplay;
  return f && f.length > 0 ? f : props.waferDisplay;
});

const effectiveDieFullPoints = computed<number[] | undefined>(() => {
  const f = props.fullDieDisplay;
  return f && f.length > 0 ? f : props.dieDisplay;
});

const effectiveReticleFullPoints = computed<number[] | undefined>(() => {
  const f = props.fullReticleDisplay;
  return f && f.length > 0 ? f : props.reticleDisplay;
});

</script>

<template>
  <!-- Error state -->
  <div v-if="samplesError" class="iq-state">
    <NResult
      status="error"
      :title="samplesError"
      description="Failed to load inspection samples"
    >
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
    }"
    :style="quadStyle"
  >
    <!-- Left column: Wafer/Die Map (top) + Sample Data (bottom) -->
    <div ref="leftPanelEl" class="iq-panel-left" :style="leftPanelStyle">
      <div class="iq-wafer">
        <ScMapPanel
          :active-map-tab="activeMapTab"
          :wafer-points="waferDisplay"
          :wafer-full-points="effectiveWaferFullPoints"
          :die-points="dieDisplay"
          :die-full-points="effectiveDieFullPoints"
          :reticle-points="reticleDisplay"
          :reticle-full-points="effectiveReticleFullPoints"
          :class-list="classList"
          :wafer-geometry="waferGeometry"
          :wafer-radius-nm="waferGeometry?.waferRadiusNm ?? undefined"
          :reticle-x-die-count="reticleOptionsModel.xDieCount"
          :reticle-y-die-count="reticleOptionsModel.yDieCount"
          :reticle-die-size-x="reticleDieSizeXModel"
          :reticle-die-size-y="reticleDieSizeYModel"
          :reticle-options="reticleOptionsModel"
          :selected-ids="mapSelectedDefectIds"
          :zoom="zoom"
          :map-loading="mapLoading"
          :map-error="mapError"
          @update:active-map-tab="(v) => emit('update:activeMapTab', v)"
          @update:reticle-options="(v) => emit('update:reticleOptions', v)"
          @select-points="onSelectPoints"
          @filter-region="onFilterRegion"
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
        :key="selectionVersion"
        :defect-ids="filteredDefectIds"
        :inspection-time="inspectionTime"
        :wafer-key="waferKey"
        :loading="false"
        :total="filteredTotal"
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
    <div class="iq-panel-right">
      <ScPreviewBlinkVirtualTable
        :key="selectionVersion"
        :samples="filteredSamples"
        :review-samples="filteredReviewSamples"
        :review-loading="reviewLoading"
        :review-error="reviewError"
        :blink-interval-ms="800"
        :initial-blink-enabled="true"
        :selected-defect-ids="selectedDefectIds"
      />
    </div>
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
  display: grid;
  grid-template-rows: minmax(0, 1fr);
  gap: 0;
  overflow: hidden;
}

.iq-quad--column-resizing {
  cursor: col-resize;
}

.iq-quad--row-resizing {
  cursor: row-resize;
}

.iq-quad--column-resizing,
.iq-quad--row-resizing {
  user-select: none;
}

.iq-quad--column-resizing *,
.iq-quad--row-resizing * {
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
  background: var(--cv-card-bg, #1a1a2e);
  border: 1px solid var(--cv-border, rgba(255, 255, 255, 0.1));
  border-radius: 8px;
  padding: 8px 10px;
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
.iq-quad--row-resizing .iq-splitter--row::before {
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

.iq-panel-right > * {
  flex: 1;
  min-height: 0;
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
