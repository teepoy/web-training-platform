<!--
  ScReticleMap — Wrapper around SimpleReticleMap with selection / zoom-in mode.
-->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import SimpleReticleMap from "./SimpleReticleMap.vue";
import type { SimpleMapPoint } from "./SimpleMapPoint";
import { classColor, STRIDE } from "./scMapUtils";

const props = defineProps<{
  xDieCount: number;
  yDieCount: number;
  dieSizeX: number;
  dieSizeY: number;
  points?: number[];
  fullPoints?: number[];
  selectedIds?: Set<number>;
  zoom?: { x: number; y: number; w: number; h: number } | null;
  mode?: "select" | "zoomin";
}>();

const emit = defineEmits<{
  (e: "filter-region", region: { x: number; y: number; w: number; h: number }): void;
  (e: "zoom-in", viewport: { x: number; y: number; w: number; h: number } | null): void;
}>();

const mode = computed(() => props.mode ?? "select");
const containerRef = ref<HTMLDivElement | null>(null);
const overlayRef = ref<HTMLCanvasElement | null>(null);

const colorMap = computed<Record<string, string>>(() => {
  const pts = props.points;
  if (!pts || pts.length === 0) return {};
  const classes = new Set<number>();
  for (let i = 0; i < pts.length; i += STRIDE) classes.add(pts[i + 3]);
  const map: Record<string, string> = {};
  for (const cn of classes) map[String(cn)] = classColor(cn);
  return map;
});

const simplePoints = computed<SimpleMapPoint[]>(() => {
  const pts = props.points;
  if (!pts || pts.length === 0) return [];
  const selected = props.selectedIds ?? new Set<number>();
  const count = Math.floor(pts.length / STRIDE);
  const result: SimpleMapPoint[] = new Array(count);
  for (let i = 0, pi = 0; pi < count; i += STRIDE, pi++) {
    result[pi] = { x: pts[i], y: pts[i + 1], id: pts[i + 2], label: String(pts[i + 3]), hasImageFlag: pts[i + 5] !== 0, isSelectedFlag: selected.has(pts[i + 2]) };
  }
  return result;
});

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
      const px = (Mx - mx) * 0.05; const py = (My - my) * 0.05;
      _s = Math.min((_cw * 0.9) / (Mx - mx + 2 * px), (_ch * 0.9) / (My - my + 2 * py));
      _ox = -(mx - px + Mx + px) / 2; _oy = -(my - py + My + py) / 2;
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

function onPointerDown(e: PointerEvent) { if (e.button !== 0) return; const [sx, sy] = getPos(e); dStart.value = dEnd.value = { x: sx, y: sy }; dragging.value = true; }
function onPointerMove(e: PointerEvent) { if (!dragging.value) return; const [sx, sy] = getPos(e); let ax = sx, ay = sy; const rw = Math.abs(sx - dStart.value.x); const rh = Math.abs(sy - dStart.value.y); if (mode.value === "zoomin" && rw > 0 && rh > 0 && _cw > 0 && _ch > 0) { const ar = _cw / _ch; const rar = rw / rh; if (rar > ar) { const ah = rw / ar; const s = Math.sign(sy - dStart.value.y) || 1; ay = dStart.value.y + s * ah; } else if (rar < ar) { const aw = rh * ar; const s = Math.sign(sx - dStart.value.x) || 1; ax = dStart.value.x + s * aw; } } dEnd.value = { x: ax, y: ay }; dragRect.value = { x: Math.min(dStart.value.x, ax), y: Math.min(dStart.value.y, ay), w: Math.abs(ax - dStart.value.x), h: Math.abs(ay - dStart.value.y) }; drawOverlay(); }
function onPointerUp() { if (!dragging.value) return; dragging.value = false; if (Math.abs(dEnd.value.x - dStart.value.x) < 4 || Math.abs(dEnd.value.y - dStart.value.y) < 4) { dragRect.value = null; drawOverlay(); return; } recalcTransform(); const [x1, y1] = screenToData(dStart.value.x, dStart.value.y); const [x2, y2] = screenToData(dEnd.value.x, dEnd.value.y); const x = Math.min(x1, x2), X = Math.max(x1, x2), y = Math.min(y1, y2), Y = Math.max(y1, y2); if (mode.value === "zoomin") { emit("zoom-in", { x, y, w: X - x, h: Y - y }); } else { emit("filter-region", { x, y, w: X - x, h: Y - y }); } dragRect.value = null; drawOverlay(); }
function drawOverlay() { const c = overlayRef.value; if (!c || _cw <= 0 || _ch <= 0) return; const ctx = c.getContext("2d"); if (!ctx) return; if (c.width !== _cw || c.height !== _ch) { c.width = _cw; c.height = _ch; } ctx.clearRect(0, 0, _cw, _ch); const r = dragRect.value; if (!r) return; ctx.fillStyle = mode.value === "zoomin" ? "rgba(34,197,94,0.15)" : "rgba(59,130,246,0.15)"; ctx.fillRect(r.x, r.y, r.w, r.h); ctx.strokeStyle = mode.value === "zoomin" ? "#22c55e" : "#3b82f6"; ctx.lineWidth = 1; ctx.strokeRect(r.x, r.y, r.w, r.h); }

function onDblClick() { if (mode.value === "zoomin" && props.zoom) emit("zoom-in", null); }

let _ro: ResizeObserver | null = null;
watch(containerRef, (el) => { _ro?.disconnect(); if (el) { _ro = new ResizeObserver(() => recalcTransform()); _ro.observe(el); } }, { immediate: true });
watch(() => props.zoom, () => recalcTransform());
</script>

<template>
  <div ref="containerRef" class="srm-wrap">
    <SimpleReticleMap
      :points="simplePoints"
      :colorMap="colorMap"
      :xDieCount="xDieCount"
      :yDieCount="yDieCount"
      :dieSizeX="dieSizeX"
      :dieSizeY="dieSizeY"
      :zoom="props.zoom ?? undefined"
    />
    <canvas ref="overlayRef" class="srm-ol" @pointerdown="onPointerDown" @pointermove="onPointerMove" @pointerup="onPointerUp" @pointercancel="onPointerUp" @pointerleave="onPointerUp" @dblclick="onDblClick" />
  </div>
</template>

<style scoped>
.srm-wrap { position: relative; width: 100%; height: 100%; display: flex; flex-direction: column; min-height: 0; }
.srm-ol { position: absolute; inset: 0; pointer-events: auto; touch-action: none; z-index: 1; }
</style>
