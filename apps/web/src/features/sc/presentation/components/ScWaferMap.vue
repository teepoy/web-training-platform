<!--
  ScWaferMap — Wrapper around SimpleWaferMap with selection / zoom-in mode.
  Data format: flat array with 6 int32 values per point:
    [x, y, defect_id, class_number, rough_bin, has_review, x, y, ...]
-->
<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import SimpleWaferMap from "./SimpleWaferMap.vue";
import type { SimpleMapPoint } from "./SimpleMapPoint";
import type { HighlightDefect, MapPointVisual } from "./types";
import { classColor, getPackedPointIdsInRegion } from "./scMapUtils";

const STRIDE = 6;
const DEFAULT_WAFER_RADIUS_NM = 150_000_000;

interface WaferGeometry {
  centerX: number;
  centerY: number;
  originX: number;
  originY: number;
  dieSizeX: number;
  dieSizeY: number;
}

const props = defineProps<{
  points?: number[];
  waferRadiusNm?: number;
  geometry?: WaferGeometry | null;
  selectedIds?: Set<number>;
  highlightDefects?: HighlightDefect[];
  pointVisualsByDefectId?: Record<string, MapPointVisual>;
  zoom?: { x: number; y: number; w: number; h: number } | null;
  mode?: "select" | "zoomin";
  queryBoxSelection?: (region: { x: number; y: number; w: number; h: number }) => Promise<number[]>;
}>();

const emit = defineEmits<{
  (e: "selection-change", ids: number[]): void;
  (e: "zoom-in", viewport: { x: number; y: number; w: number; h: number } | null): void;
}>();

type Mode = "select" | "zoomin";
const mode = computed(() => props.mode ?? "select");

const isBoxSelecting = ref(false);
let selectionSeq = 0;

const containerRef = ref<HTMLDivElement | null>(null);
const overlayRef = ref<HTMLCanvasElement | null>(null);

const waferRadiusNm = computed(() => props.waferRadiusNm ?? DEFAULT_WAFER_RADIUS_NM);
const pointCount = computed(() => Math.floor((props.points?.length ?? 0) / STRIDE));

const colorMap = computed<Record<string, string>>(() => {
  const pts = props.points;
  if (!pts || pts.length === 0) return {};
  const classes = new Set<number>();
  for (let i = 0; i < pts.length; i += STRIDE) classes.add(pts[i + 3]);
  const map: Record<string, string> = {};
  for (const cn of classes) map[String(cn)] = classColor(cn);
  for (const visual of Object.values(props.pointVisualsByDefectId ?? {})) {
    map[visual.label] = visual.color;
  }
  return map;
});

const simplePoints = computed<SimpleMapPoint[]>(() => {
  const pts = props.points;
  if (!pts || pts.length === 0) return [];
  const selected = props.selectedIds ?? new Set<number>();
  const count = Math.floor(pts.length / STRIDE);
  const result: SimpleMapPoint[] = new Array(count);
  for (let i = 0, pi = 0; pi < count; i += STRIDE, pi++) {
    const defectId = pts[i + 2];
    const visual = props.pointVisualsByDefectId?.[String(defectId)];
    result[pi] = {
      x: pts[i], y: pts[i + 1], id: defectId,
      label: visual?.label ?? String(pts[i + 3]),
      hasImageFlag: pts[i + 5] !== 0,
      isSelectedFlag: selected.has(defectId),
    };
  }
  return result;
});

// ── Coordinate transform (mirrors SimpleWaferMap internals) ──

let _cw = 600; let _ch = 600;
let _cx = 300; let _cy = 300;
let _s = 1; let _ox = 0; let _oy = 0;

function recalcTransform() {
  if (!containerRef.value) return;
  _cw = containerRef.value.clientWidth || 1;
  _ch = containerRef.value.clientHeight || 1;
  _cx = _cw / 2; _cy = _ch / 2;
  const cx = props.geometry?.centerX ?? 0;
  const cy = props.geometry?.centerY ?? 0;
  if (props.zoom) {
    const z = props.zoom;
    _s = Math.min((_cw * 0.95) / z.w, (_ch * 0.95) / z.h);
    _ox = -(z.x + z.w / 2);
    _oy = -(z.y + z.h / 2);
  } else {
    _s = Math.min(_cw, _ch) / (2 * waferRadiusNm.value);
    _ox = -cx;
    _oy = -cy;
  }
}

function screenToData(sx: number, sy: number): [number, number] {
  return [(sx - _cx) / _s - _ox, (_cy - sy) / _s - _oy];
}

function getPos(e: MouseEvent): [number, number] {
  const rect = containerRef.value?.getBoundingClientRect();
  if (!rect) return [0, 0];
  return [e.clientX - rect.left, e.clientY - rect.top];
}

// ── Drag ──

const dragging = ref(false);
const dragStart = ref({ x: 0, y: 0 });
const dragEnd = ref({ x: 0, y: 0 });
const dragRect = ref<{ x: number; y: number; w: number; h: number } | null>(null);

function onPointerDown(e: PointerEvent) {
  if (e.button !== 0) return;
  recalcTransform();
  drawOverlay();
  const [sx, sy] = getPos(e);
  dragStart.value = { x: sx, y: sy };
  dragEnd.value = { x: sx, y: sy };
  dragging.value = true;
}

function onPointerMove(e: PointerEvent) {
  if (!dragging.value) return;
  const [sx, sy] = getPos(e);

  let ax = sx, ay = sy;
  if (mode.value === "zoomin") {
    const rawW = Math.abs(sx - dragStart.value.x);
    const rawH = Math.abs(sy - dragStart.value.y);
    if (rawW > 0 && rawH > 0 && _cw > 0 && _ch > 0) {
      const ar = _cw / _ch;
      const rawAR = rawW / rawH;
      if (rawAR > ar) {
        const adjH = rawW / ar;
        const sign = Math.sign(sy - dragStart.value.y) || 1;
        ay = dragStart.value.y + sign * adjH;
      } else if (rawAR < ar) {
        const adjW = rawH * ar;
        const sign = Math.sign(sx - dragStart.value.x) || 1;
        ax = dragStart.value.x + sign * adjW;
      }
    }
  }

  dragEnd.value = { x: ax, y: ay };
  dragRect.value = {
    x: Math.min(dragStart.value.x, ax),
    y: Math.min(dragStart.value.y, ay),
    w: Math.abs(ax - dragStart.value.x),
    h: Math.abs(ay - dragStart.value.y),
  };
  drawOverlay();
}

function onPointerUp(e: PointerEvent) {
  if (!dragging.value) return;
  dragging.value = false;
  const dx = Math.abs(dragEnd.value.x - dragStart.value.x);
  const dy = Math.abs(dragEnd.value.y - dragStart.value.y);

  if (dx < 4 || dy < 4) { dragRect.value = null; drawOverlay(); return; }

  recalcTransform();
  const [d1x, d1y] = screenToData(dragStart.value.x, dragStart.value.y);
  const [d2x, d2y] = screenToData(dragEnd.value.x, dragEnd.value.y);
  const x = Math.min(d1x, d2x), X = Math.max(d1x, d2x);
  const y = Math.min(d1y, d2y), Y = Math.max(d1y, d2y);

  if (mode.value === "zoomin") {
    emit("zoom-in", { x, y, w: X - x, h: Y - y });
  } else {
    void handleBoxSelect({ x, y, w: X - x, h: Y - y });
  }

  dragRect.value = null;
  drawOverlay();
}

function drawOverlay() {
  const cvs = overlayRef.value;
  if (!cvs || _cw <= 0 || _ch <= 0) return;
  const ctx = cvs.getContext("2d");
  if (!ctx) return;
  if (cvs.width !== _cw || cvs.height !== _ch) { cvs.width = _cw; cvs.height = _ch; }
  ctx.clearRect(0, 0, _cw, _ch);

  // Draw highlight defects as cyan 3x3 dots
  if (props.highlightDefects && props.highlightDefects.length > 0) {
    ctx.fillStyle = "#00FFFF";
    for (const hd of props.highlightDefects) {
      const sx = (hd.waferX + _ox) * _s + _cx;
      const sy = _cy - (hd.waferY + _oy) * _s;
      ctx.fillRect(sx - 1.5, sy - 1.5, 3, 3);
    }
  }

  const r = dragRect.value;
  if (!r) return;
  const fill = mode.value === "zoomin" ? "rgba(34,197,94,0.15)" : "rgba(59,130,246,0.15)";
  const stroke = mode.value === "zoomin" ? "#22c55e" : "#3b82f6";
  ctx.fillStyle = fill;
  ctx.fillRect(r.x, r.y, r.w, r.h);
  ctx.strokeStyle = stroke;
  ctx.lineWidth = 1;
  ctx.strokeRect(r.x, r.y, r.w, r.h);
}

function onDblClick() {
  if (mode.value === "zoomin" && props.zoom) {
    emit("zoom-in", null);
  } else if (mode.value === "select") {
    selectionSeq += 1;
    emit("selection-change", []);
  }
}

// ── Box select handler ──
async function handleBoxSelect(region: { x: number; y: number; w: number; h: number }) {
  const thisSeq = ++selectionSeq;
  const immediateIds = getPackedPointIdsInRegion(props.points ?? [], region);
  const currentIds = props.selectedIds ?? new Set<number>();
  const merged = new Set([...currentIds, ...immediateIds]);
  emit("selection-change", [...merged]);

  if (!props.queryBoxSelection) {
    return;
  }
  isBoxSelecting.value = true;
  try {
    const ids = await props.queryBoxSelection(region);
    if (thisSeq !== selectionSeq) return;
    const next = new Set([...currentIds, ...ids]);
    if (next.size !== currentIds.size) {
      emit("selection-change", [...next]);
    }
  } finally {
    isBoxSelecting.value = false;
  }
}

// ── Resize ──

let _ro: ResizeObserver | null = null;
function onResize() { recalcTransform(); drawOverlay(); }

watch(containerRef, (el) => {
  _ro?.disconnect();
  if (el) { _ro = new ResizeObserver(onResize); _ro.observe(el); }
}, { immediate: true });

function scheduleOverlayRefresh(): void {
  void nextTick(() => {
    recalcTransform();
    drawOverlay();
    window.requestAnimationFrame(() => {
      recalcTransform();
      drawOverlay();
    });
  });
}

watch([pointCount, overlayRef], scheduleOverlayRefresh, { immediate: true });

watch(() => props.zoom, () => { recalcTransform(); drawOverlay(); });

watch(() => props.highlightDefects, () => { drawOverlay(); });

watch(() => props.geometry, (geo) => {
  recalcTransform();
  drawOverlay();
}, { immediate: true });
</script>

<template>
  <div ref="containerRef" class="swm-wrap">
    <div v-if="pointCount === 0" class="swm-empty">No points</div>
    <template v-else>
      <SimpleWaferMap
        :points="simplePoints"
        :colorMap="colorMap"
        :zoom="props.zoom ?? undefined"
        :center-x="props.geometry?.centerX"
        :center-y="props.geometry?.centerY"
        :origin-x="props.geometry?.originX"
        :origin-y="props.geometry?.originY"
        :die-size-x="props.geometry?.dieSizeX"
        :die-size-y="props.geometry?.dieSizeY"
      />
      <canvas
        ref="overlayRef"
        class="swm-ol"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointercancel="onPointerUp"
        @pointerleave="onPointerUp"
        @dblclick="onDblClick"
      />
      <div class="swm-footer">{{ pointCount }} points</div>
    </template>
  </div>
</template>

<style scoped>
.swm-wrap { position: relative; width: 100%; height: 100%; display: flex; flex-direction: column; min-height: 0; }
.swm-ol { position: absolute; inset: 0; pointer-events: auto; touch-action: none; z-index: 1; }
.swm-empty, .swm-footer { padding: 6px; color: #888; font-size: 12px; text-align: center; }
.swm-empty { margin: auto; }
.swm-footer { position: absolute; right: 0; bottom: 0; pointer-events: none; }
</style>
