<!--
  ScDieStackMap — Wrapper around SimpleDieStackMap with selection / zoom-in mode.
-->
<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import SimpleDieStackMap from "./SimpleDieStackMap.vue";
import type { SimpleMapPoint } from "./SimpleMapPoint";
import type { HighlightDefect } from "./types";
import { getPackedPointIdsInRegion, STRIDE } from "./scMapUtils";
import type { ScBoxRegion } from "@/features/sc/api/boxFilter";

const HIGHLIGHT_POINT_COLOR = "#A855F7";

const props = defineProps<{
  points?: number[];
  dieSizeX?: number;
  dieSizeY?: number;
  selectedIds?: Set<number>;
  highlightDefects?: HighlightDefect[];
  colorMap?: Record<string, string>;
  zoom?: { x: number; y: number; w: number; h: number } | null;
  mode?: "select" | "zoomin";
  queryBoxSelection?: (region: ScBoxRegion) => Promise<number[]>;
}>();

const emit = defineEmits<{
  (e: "selection-change", ids: number[]): void;
  (e: "zoom-in", viewport: { x: number; y: number; w: number; h: number } | null): void;
}>();

const mode = computed(() => props.mode ?? "select");
const containerRef = ref<HTMLDivElement | null>(null);
const overlayRef = ref<HTMLCanvasElement | null>(null);
const selectionState = ref<Set<number>>(new Set());
const isBoxSelecting = ref(false);
let selectionSeq = 0;

const simplePoints = computed<SimpleMapPoint[]>(() => {
  const pts = props.points;
  if (!pts || pts.length === 0) return [];
  const sel = selectionState.value;
  const count = Math.floor(pts.length / STRIDE);
  const result: SimpleMapPoint[] = new Array(count);
  for (let i = 0, pi = 0; pi < count; i += STRIDE, pi++) {
    const defectId = pts[i + 2];
    result[pi] = { x: pts[i], y: pts[i + 1], id: defectId, label: String(pts[i + 3]), hasImageFlag: pts[i + 5] !== 0, isSelectedFlag: sel.has(defectId) };
  }
  return result;
});
const pointCount = computed(() => simplePoints.value.length);

// Transform
let _cw = 600; let _ch = 240; let _cx = 300; let _cy = 120; let _s = 1; let _ox = 0; let _oy = 0;

function recalcTransform() {
  if (!containerRef.value) return;
  _cw = containerRef.value.clientWidth || 1;
  _ch = containerRef.value.clientHeight || 1;
  _cx = _cw / 2; _cy = _ch / 2;
  if (props.zoom) {
    const z = props.zoom;
    _s = Math.min((_cw * 0.95) / z.w, (_ch * 0.95) / z.h);
    _ox = -(z.x + z.w / 2); _oy = -(z.y + z.h / 2);
  } else {
    const pts = simplePoints.value;
    if (pts.length > 0) {
      let mx = pts[0].x, Mx = pts[0].x, my = pts[0].y, My = pts[0].y;
      for (const p of pts) { if (p.x < mx) mx = p.x; if (p.x > Mx) Mx = p.x; if (p.y < my) my = p.y; if (p.y > My) My = p.y; }
      if (mx === Mx) { mx -= 0.5; Mx += 0.5; } if (my === My) { my -= 0.5; My += 0.5; }
      _s = Math.min((_cw * 0.9) / (Mx - mx), (_ch * 0.9) / (My - my));
      _ox = -(mx + Mx) / 2; _oy = -(my + My) / 2;
    }
  }
}

function screenToData(sx: number, sy: number): [number, number] { return [(sx - _cx) / _s - _ox, (_cy - sy) / _s - _oy]; }
function getPos(e: MouseEvent): [number, number] { const r = containerRef.value?.getBoundingClientRect(); return r ? [e.clientX - r.left, e.clientY - r.top] : [0, 0]; }

// Drag
const dragging = ref(false);
const dStart = ref({ x: 0, y: 0 });
const dEnd = ref({ x: 0, y: 0 });
const dragRect = ref<{ x: number; y: number; w: number; h: number } | null>(null);

function onPointerDown(e: PointerEvent) { if (e.button !== 0) return; recalcTransform(); drawOverlay(); const [sx, sy] = getPos(e); dStart.value = dEnd.value = { x: sx, y: sy }; dragging.value = true; }
function onPointerMove(e: PointerEvent) { if (!dragging.value) return; const [sx, sy] = getPos(e); let ax = sx, ay = sy; const rw = Math.abs(sx - dStart.value.x); const rh = Math.abs(sy - dStart.value.y); if (mode.value === "zoomin" && rw > 0 && rh > 0 && _cw > 0 && _ch > 0) { const ar = _cw / _ch; const rar = rw / rh; if (rar > ar) { const ah = rw / ar; const s = Math.sign(sy - dStart.value.y) || 1; ay = dStart.value.y + s * ah; } else if (rar < ar) { const aw = rh * ar; const s = Math.sign(sx - dStart.value.x) || 1; ax = dStart.value.x + s * aw; } } dEnd.value = { x: ax, y: ay }; dragRect.value = { x: Math.min(dStart.value.x, ax), y: Math.min(dStart.value.y, ay), w: Math.abs(ax - dStart.value.x), h: Math.abs(ay - dStart.value.y) }; drawOverlay(); }
async function onPointerUp() { if (!dragging.value) return; dragging.value = false; if (Math.abs(dEnd.value.x - dStart.value.x) < 4 || Math.abs(dEnd.value.y - dStart.value.y) < 4) { dragRect.value = null; drawOverlay(); return; } recalcTransform(); const [x1, y1] = screenToData(dStart.value.x, dStart.value.y); const [x2, y2] = screenToData(dEnd.value.x, dEnd.value.y); const x = Math.min(x1, x2), X = Math.max(x1, x2), y = Math.min(y1, y2), Y = Math.max(y1, y2); if (mode.value === "zoomin") { emit("zoom-in", { x, y, w: X - x, h: Y - y }); } else { const thisSeq = ++selectionSeq; const region = { x, y, w: X - x, h: Y - y }; const immediateIds = getPackedPointIdsInRegion(props.points ?? [], region); selectionState.value = new Set([...selectionState.value, ...immediateIds]); emit("selection-change", [...selectionState.value]); if (props.queryBoxSelection) { isBoxSelecting.value = true; try { const ids = await props.queryBoxSelection(region); if (thisSeq !== selectionSeq) return; const next = new Set([...selectionState.value, ...ids]); if (next.size !== selectionState.value.size) { selectionState.value = next; emit("selection-change", [...selectionState.value]); } } finally { isBoxSelecting.value = false; } } } dragRect.value = null; drawOverlay(); }
function drawOverlay() {
  const c = overlayRef.value;
  if (!c || _cw <= 0 || _ch <= 0) return;
  const ctx = c.getContext("2d");
  if (!ctx) return;
  if (c.width !== _cw || c.height !== _ch) { c.width = _cw; c.height = _ch; }
  ctx.clearRect(0, 0, _cw, _ch);

  // Draw highlight defects as purple 3x3 dots
  if (props.highlightDefects && props.highlightDefects.length > 0) {
    ctx.fillStyle = HIGHLIGHT_POINT_COLOR;
    for (const hd of props.highlightDefects) {
      const sx = (hd.dieX + _ox) * _s + _cx;
      const sy = _cy - (hd.dieY + _oy) * _s;
      ctx.fillRect(sx - 1.5, sy - 1.5, 3, 3);
    }
  }

  const r = dragRect.value;
  if (!r) return;
  ctx.fillStyle = mode.value === "zoomin" ? "rgba(34,197,94,0.15)" : "rgba(59,130,246,0.15)";
  ctx.fillRect(r.x, r.y, r.w, r.h);
  ctx.strokeStyle = mode.value === "zoomin" ? "#22c55e" : "#3b82f6";
  ctx.lineWidth = 1;
  ctx.strokeRect(r.x, r.y, r.w, r.h);
}

function onDblClick() {
  if (mode.value === "zoomin" && props.zoom) {
    emit("zoom-in", null);
  } else if (mode.value === "select") {
    selectionSeq += 1;
    selectionState.value = new Set();
    emit("selection-change", []);
  }
}

let _ro: ResizeObserver | null = null;
watch(containerRef, (el) => { _ro?.disconnect(); if (el) { _ro = new ResizeObserver(() => { recalcTransform(); drawOverlay(); }); _ro.observe(el); } }, { immediate: true });

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
watch(() => props.selectedIds, (newSelected) => {
  if (isBoxSelecting.value || !newSelected) return;
  const cur = selectionState.value;
  let changed = false;
  for (const id of newSelected) { if (!cur.has(id)) { cur.add(id); changed = true; } }
  for (const id of cur) { if (!newSelected.has(id)) { cur.delete(id); changed = true; } }
  if (changed) selectionState.value = new Set(cur);
}, { immediate: true });

watch(() => props.highlightDefects, () => { drawOverlay(); });
</script>

<template>
  <div ref="containerRef" class="sdsm-wrap">
    <div v-if="pointCount === 0" class="sdsm-empty">No points</div>
    <template v-else>
      <SimpleDieStackMap
        :points="simplePoints"
        :colorMap="props.colorMap ?? {}"
        :die-size-x="dieSizeX"
        :die-size-y="dieSizeY"
        :zoom="props.zoom ?? undefined"
      />
      <canvas ref="overlayRef" class="sdsm-ol" @pointerdown="onPointerDown" @pointermove="onPointerMove" @pointerup="onPointerUp" @pointercancel="onPointerUp" @pointerleave="onPointerUp" @dblclick="onDblClick" />
    </template>
  </div>
</template>

<style scoped>
.sdsm-wrap { position: relative; width: 100%; height: 100%; display: flex; flex-direction: column; min-height: 0; }
.sdsm-ol { position: absolute; inset: 0; pointer-events: auto; touch-action: none; z-index: 1; }
.sdsm-empty { align-items: center; color: var(--text-color-3); display: flex; inset: 0; justify-content: center; position: absolute; }
.sdsm-footer { bottom: 8px; color: var(--text-color-3); font-size: 12px; pointer-events: none; position: absolute; right: 10px; }
</style>
