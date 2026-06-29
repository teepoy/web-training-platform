<script setup lang="ts">
import { computed, onUpdated, ref, watch } from "vue";
import SimplePerspectiveMap from "./SimplePerspectiveMap.vue";
import type { HighlightDefect } from "./types";
import type { MapDisplayArray } from "./transforms/binsToDisplayArrays";
import {
  boundsFromRegion,
  buildMapTransform,
  constrainDragToAspect,
  dataToScreen,
  eventToLocalPoint,
  measureMapElement,
  prepareOverlayCanvas,
  screenToData,
  type ScMapSize,
  type ScMapTransform,
} from "./scMapViewport";

const STRIDE = 6;
const DEFAULT_WAFER_RADIUS_NM = 150_000_000;

const DIE_LINE_COLOR = "#9ca3af";
const WAFER_EDGE_COLOR = "#333333";

interface WaferGeometry {
  centerX: number;
  centerY: number;
  originX: number;
  originY: number;
  dieSizeX: number;
  dieSizeY: number;
}

const props = defineProps<{
  points?: MapDisplayArray | number[];
  waferRadiusNm?: number;
  geometry?: WaferGeometry | null;
  colorMap?: Record<string, string>;
  zoom?: { x: number; y: number; w: number; h: number } | null;
  mode?: "select" | "zoomin";
  queryBoxSelection?: (region: { x: number; y: number; w: number; h: number }) => Promise<number[]>;
  highlightDefects?: HighlightDefect[];
  immediateCrosshairPoints?: Array<{ x: number; y: number }>;
  immediateCrosshairVersion?: number;
}>();

const emit = defineEmits<{
  (e: "selection-change", ids: number[]): void;
  (e: "zoom-in", viewport: { x: number; y: number; w: number; h: number } | null): void;
  (e: "box-select", region: { x: number; y: number; w: number; h: number }): void;
  (e: "immediate-crosshair-points", points: Array<{ x: number; y: number }>): void;
}>();

type Mode = "select" | "zoomin";
const mode = computed(() => props.mode ?? "select");

let selectionSeq = 0;

const immediateCrosshairPoints = ref<{ x: number; y: number }[]>([]);
const HIGHLIGHT_POINT_COLOR = "#A855F7";
const CROSSHAIR_COLOR = "#000000";

const containerRef = ref<HTMLDivElement | null>(null);
const bgRef = ref<HTMLCanvasElement | null>(null);
const overlayRef = ref<HTMLCanvasElement | null>(null);

let mapSize: ScMapSize = { width: 600, height: 600 };
let transform: ScMapTransform = buildMapTransform(
  mapSize,
  {
    minX: -DEFAULT_WAFER_RADIUS_NM,
    maxX: DEFAULT_WAFER_RADIUS_NM,
    minY: -DEFAULT_WAFER_RADIUS_NM,
    maxY: DEFAULT_WAFER_RADIUS_NM,
  },
  1,
);

let dieGridData: { x: number; y: number; valid: boolean }[] = [];
let gridExtent = 0;

function buildDieGrid(
  radiusNm: number,
  gCenterX: number,
  gCenterY: number,
  gOriginX: number,
  gOriginY: number,
  dieSX: number,
  dieSY: number,
) {
  dieGridData = [];
  const dw = Math.max(1, dieSX);
  const dh = Math.max(1, dieSY);
  const screenDieW = dw * transform.scale;
  const screenDieH = dh * transform.scale;
  if (screenDieW < 0.5 && screenDieH < 0.5) return;

  const z = props.zoom;
  const minX = z ? z.x : gCenterX - radiusNm;
  const maxX = z ? z.x + z.w : gCenterX + radiusNm;
  const minY = z ? z.y : gCenterY - radiusNm;
  const maxY = z ? z.y + z.h : gCenterY + radiusNm;

  const ixStart = Math.floor((minX - gOriginX) / dw) - 1;
  const ixEnd = Math.ceil((maxX - gOriginX) / dw) + 1;
  const iyStart = Math.floor((minY - gOriginY) / dh) - 1;
  const iyEnd = Math.ceil((maxY - gOriginY) / dh) + 1;

  gridExtent = Math.max(Math.abs(ixStart), Math.abs(ixEnd), Math.abs(iyStart), Math.abs(iyEnd));

  const totalCells = (ixEnd - ixStart + 1) * (iyEnd - iyStart + 1);
  if (totalCells > 50_000) return;

  const r = radiusNm;
  for (let ix = ixStart; ix <= ixEnd; ix++) {
    for (let iy = iyStart; iy <= iyEnd; iy++) {
      const left = gOriginX + ix * dw;
      const top = gOriginY + iy * dh;
      const right = left + dw;
      const bottom = top + dh;

      if (z && (right < z.x || left > z.x + z.w || bottom < z.y || top > z.y + z.h)) continue;

      const clampX = Math.max(left, Math.min(gCenterX, right));
      const clampY = Math.max(top, Math.min(gCenterY, bottom));
      const distToCenter = Math.hypot(clampX - gCenterX, clampY - gCenterY);
      if (distToCenter > r) continue;

      const d1 = Math.hypot(left - gCenterX, top - gCenterY);
      const d2 = Math.hypot(right - gCenterX, top - gCenterY);
      const d3 = Math.hypot(left - gCenterX, bottom - gCenterY);
      const d4 = Math.hypot(right - gCenterX, bottom - gCenterY);
      const maxDist = Math.max(d1, d2, d3, d4);

      dieGridData.push({ x: left, y: top, valid: maxDist <= r });
    }
  }
}

function buildWaferPath(ex: number, ey: number, r: number): Path2D {
  const notchDepth = 6;
  const notchWidth = 12;
  const notchAngle = Math.asin(Math.min(notchWidth / 2 / r, 1));
  const startAngle = Math.PI / 2 + notchAngle;
  const endAngle = Math.PI / 2 - notchAngle;

  const path = new Path2D();
  path.arc(ex, ey, r, startAngle, endAngle, false);
  path.lineTo(ex, ey + r - notchDepth);
  path.closePath();
  return path;
}

function renderBackground() {
  const cvs = bgRef.value;
  if (!cvs || mapSize.width <= 0 || mapSize.height <= 0) return;
  const ctx = prepareOverlayCanvas(cvs, mapSize);
  if (!ctx) return;

  const g = props.geometry;
  if (!g || !hasGeometry.value) return;
  const radiusNm = props.waferRadiusNm ?? DEFAULT_WAFER_RADIUS_NM;
  const gCx = g.centerX;
  const gCy = g.centerY;
  const gOx = g.originX;
  const gOy = g.originY;
  const dieSX = g.dieSizeX;
  const dieSY = g.dieSizeY;

  const z = props.zoom;
  const zMinX = z ? z.x : gCx - radiusNm;
  const zMaxX = z ? z.x + z.w : gCx + radiusNm;
  const zMinY = z ? z.y : gCy - radiusNm;
  const zMaxY = z ? z.y + z.h : gCy + radiusNm;

  if (z) {
    ctx.fillStyle = "#e8e8e8";
    ctx.fillRect(0, 0, mapSize.width, mapSize.height);

    for (const die of dieGridData) {
      const [dx, dy] = dataToScreen(transform, die.x, die.y);
      const dw = dieSX * transform.scale;
      const dh = dieSY * transform.scale;
      ctx.fillStyle = die.valid ? "#ffffff" : "#9ca3af";
      const left = Math.round(dx);
      const right = Math.round(dx + dw);
      const top = Math.round(dy - dh);
      const bottom = Math.round(dy);
      ctx.fillRect(left, top, right - left, bottom - top);
    }

    ctx.beginPath();
    ctx.strokeStyle = DIE_LINE_COLOR;
    ctx.lineWidth = 1;

    const ixMin = Math.floor((zMinX - gOx) / dieSX);
    const ixMax = Math.ceil((zMaxX - gOx) / dieSX);
    const iyMin = Math.floor((zMinY - gOy) / dieSY);
    const iyMax = Math.ceil((zMaxY - gOy) / dieSY);

    for (let ix = ixMin; ix <= ixMax + 1; ix++) {
      const dataX = gOx + ix * dieSX;
      const [sx] = dataToScreen(transform, dataX, 0);
      const [, sy1] = dataToScreen(transform, 0, zMinY);
      const [, sy2] = dataToScreen(transform, 0, zMaxY);
      ctx.moveTo(Math.round(sx) + 0.5, sy1);
      ctx.lineTo(Math.round(sx) + 0.5, sy2);
    }
    for (let iy = iyMin; iy <= iyMax + 1; iy++) {
      const dataY = gOy + iy * dieSY;
      const [sx1] = dataToScreen(transform, zMinX, 0);
      const [sx2] = dataToScreen(transform, zMaxX, 0);
      const [, sy] = dataToScreen(transform, 0, dataY);
      ctx.moveTo(sx1, Math.round(sy) + 0.5);
      ctx.lineTo(sx2, Math.round(sy) + 0.5);
    }
    ctx.stroke();

    ctx.strokeStyle = WAFER_EDGE_COLOR;
    ctx.lineWidth = 2;
    ctx.strokeRect(1, 1, mapSize.width - 2, mapSize.height - 2);
  } else {
    const [ex, ey] = dataToScreen(transform, gCx, gCy);
    const r = radiusNm * transform.scale;

    const waferPath = buildWaferPath(ex, ey, r);

    ctx.save();
    ctx.shadowColor = "rgba(0,0,0,0.12)";
    ctx.shadowBlur = 10;
    ctx.shadowOffsetY = 3;
    ctx.fillStyle = "#ffffff";
    ctx.fill(waferPath);
    ctx.restore();

    ctx.save();
    ctx.clip(waferPath);

    ctx.fillStyle = "#e8e8e8";
    ctx.fillRect(0, 0, mapSize.width, mapSize.height);

    for (const die of dieGridData) {
      const [dx, dy] = dataToScreen(transform, die.x, die.y);
      const dw = dieSX * transform.scale;
      const dh = dieSY * transform.scale;
      ctx.fillStyle = die.valid ? "#ffffff" : "#9ca3af";
      const left = Math.round(dx);
      const right = Math.round(dx + dw);
      const top = Math.round(dy - dh);
      const bottom = Math.round(dy);
      ctx.fillRect(left, top, right - left, bottom - top);
    }

    ctx.beginPath();
    ctx.strokeStyle = DIE_LINE_COLOR;
    ctx.lineWidth = 1;

    for (let ix = -gridExtent; ix <= gridExtent + 1; ix++) {
      const dataX = gOx + ix * dieSX;
      const [sx] = dataToScreen(transform, dataX, 0);
      const [, sy1] = dataToScreen(transform, 0, zMinY);
      const [, sy2] = dataToScreen(transform, 0, zMaxY);
      ctx.moveTo(Math.round(sx) + 0.5, sy1);
      ctx.lineTo(Math.round(sx) + 0.5, sy2);
    }
    for (let iy = -gridExtent; iy <= gridExtent + 1; iy++) {
      const dataY = gOy + iy * dieSY;
      const [sx1] = dataToScreen(transform, zMinX, 0);
      const [sx2] = dataToScreen(transform, zMaxX, 0);
      const [, sy] = dataToScreen(transform, 0, dataY);
      ctx.moveTo(sx1, Math.round(sy) + 0.5);
      ctx.lineTo(sx2, Math.round(sy) + 0.5);
    }
    ctx.stroke();

    ctx.restore();

    ctx.lineWidth = 2;
    ctx.strokeStyle = WAFER_EDGE_COLOR;
    ctx.stroke(waferPath);
  }
}

const hasGeometry = computed(() => {
  const g = props.geometry;
  return Boolean(g && Number.isFinite(g.centerX) && Number.isFinite(g.centerY));
});

const dataBounds = computed(() => {
  const g = props.geometry;
  if (!g || !hasGeometry.value) return undefined;
  const radius = props.waferRadiusNm ?? DEFAULT_WAFER_RADIUS_NM;
  return {
    minX: g.centerX - radius,
    maxX: g.centerX + radius,
    minY: g.centerY - radius,
    maxY: g.centerY + radius,
  };
});

const centerX = computed(() => props.geometry?.centerX ?? 0);
const centerY = computed(() => props.geometry?.centerY ?? 0);

function recalcTransform() {
  const size = measureMapElement(containerRef.value);
  if (!size || !hasGeometry.value) return;
  mapSize = size;
  const cx = centerX.value;
  const cy = centerY.value;
  const g = props.geometry;
  const radius = props.waferRadiusNm ?? DEFAULT_WAFER_RADIUS_NM;
  if (props.zoom) {
    transform = buildMapTransform(mapSize, boundsFromRegion(props.zoom), 1.0);
  } else {
    transform = buildMapTransform(
      mapSize,
      {
        minX: cx - radius,
        maxX: cx + radius,
        minY: cy - radius,
        maxY: cy + radius,
      },
      1,
    );
  }
  if (g) {
    buildDieGrid(radius, g.centerX, g.centerY, g.originX, g.originY, g.dieSizeX, g.dieSizeY);
  }
  renderBackground();
}

function getPos(e: MouseEvent): [number, number] {
  return eventToLocalPoint(containerRef.value, e);
}

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
  let ax = sx,
    ay = sy;
  if (mode.value === "zoomin") {
    ({ x: ax, y: ay } = constrainDragToAspect(dragStart.value, { x: sx, y: sy }, mapSize));
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
  if (dx < 4 || dy < 4) {
    dragRect.value = null;
    drawOverlay();
    return;
  }
  recalcTransform();
  const [d1x, d1y] = screenToData(transform, dragStart.value.x, dragStart.value.y);
  const [d2x, d2y] = screenToData(transform, dragEnd.value.x, dragEnd.value.y);
  const x = Math.min(d1x, d2x),
    X = Math.max(d1x, d2x);
  const y = Math.min(d1y, d2y),
    Y = Math.max(d1y, d2y);
  const region = { x, y, w: X - x, h: Y - y };

  if (mode.value === "zoomin") {
    emit("zoom-in", region);
  } else {
    const pts = props.points;
    const inRegion: { x: number; y: number }[] = [];
    if (pts && pts.length > 0) {
      const count = Math.floor(pts.length / STRIDE);
      for (let i = 0, pi = 0; pi < count; i += STRIDE, pi++) {
        const x = pts[i],
          y = pts[i + 1];
        if (
          x >= region.x &&
          x <= region.x + region.w &&
          y >= region.y &&
          y <= region.y + region.h
        ) {
          inRegion.push({ x, y });
        }
      }
    }
    console.debug("[ScWaferMapPerspective] immediateCrosshair", {
      count: inRegion.length,
      region,
    });
    emit("immediate-crosshair-points", inRegion);
    emit("box-select", region);
    void handleBoxSelect(region);
  }
  dragRect.value = null;
  drawOverlay();
}

async function handleBoxSelect(region: { x: number; y: number; w: number; h: number }) {
  if (!props.queryBoxSelection) return;
  const thisSeq = ++selectionSeq;
  try {
    const ids = await props.queryBoxSelection(region);
    if (thisSeq !== selectionSeq) return;
    emit("selection-change", ids);
  } catch {
    /* best effort */
  }
}

function onDblClick() {
  selectionSeq += 1;
  dragRect.value = null;
  immediateCrosshairPoints.value = [];
  if (mode.value === "zoomin" && props.zoom) emit("zoom-in", null);
  emit("immediate-crosshair-points", []);
  emit("selection-change", []);
  drawOverlay();
}

onUpdated(() => console.debug("[render] ScWaferMapPerspective"));

function drawOverlay() {
  console.debug("[map] ScWaferMap drawOverlay");
  const cvs = overlayRef.value;
  if (!cvs || mapSize.width <= 0 || mapSize.height <= 0) return;
  const ctx = prepareOverlayCanvas(cvs, mapSize);
  if (!ctx) return;

  // 1. Draw highlight defects as purple 5x5 crosshairs (from gallery selection)
  if (props.highlightDefects && props.highlightDefects.length > 0) {
    ctx.strokeStyle = HIGHLIGHT_POINT_COLOR;
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (const hd of props.highlightDefects) {
      const [cx, cy] = dataToScreen(transform, hd.waferX, hd.waferY);
      ctx.moveTo(cx - 3, cy);
      ctx.lineTo(cx + 3, cy);
      ctx.moveTo(cx, cy - 3);
      ctx.lineTo(cx, cy + 3);
    }
    ctx.stroke();
  }

  // 2. Draw immediate crosshairs (black + shape, 5x5)
  const crosshairs = immediateCrosshairPoints.value;
  if (crosshairs.length > 0) {
    ctx.strokeStyle = CROSSHAIR_COLOR;
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (const pt of crosshairs) {
      const [cx, cy] = dataToScreen(transform, pt.x, pt.y);
      ctx.moveTo(cx - 3, cy);
      ctx.lineTo(cx + 3, cy);
      ctx.moveTo(cx, cy - 3);
      ctx.lineTo(cx, cy + 3);
    }
    ctx.stroke();
  }

  // 3. Draw drag rectangle (existing logic)
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

let _ro: ResizeObserver | null = null;
function onResize() {
  recalcTransform();
  drawOverlay();
}
watch(
  containerRef,
  (el) => {
    _ro?.disconnect();
    if (el) {
      _ro = new ResizeObserver(onResize);
      _ro.observe(el);
    }
  },
  { immediate: true },
);

watch(
  () => props.points,
  () => {
    console.debug("[map] ScWaferMap watch(points) → redraw");
    recalcTransform();
    drawOverlay();
  },
);

// Clear immediate crosshairs on mode change
watch(
  () => props.mode,
  () => {
    if (immediateCrosshairPoints.value.length > 0) {
      immediateCrosshairPoints.value = [];
      emit("immediate-crosshair-points", []);
      drawOverlay();
    }
  },
);

// Redraw overlay when highlight defects change (gallery selection → map)
watch(
  () => props.highlightDefects,
  () => drawOverlay(),
);

watch(
  [() => props.immediateCrosshairVersion, () => props.immediateCrosshairPoints],
  ([version]) => {
    if (version == null) return;
    const points = props.immediateCrosshairPoints ?? [];
    immediateCrosshairPoints.value = [...points];
    drawOverlay();
  },
  { immediate: true },
);
</script>

<template>
  <div ref="containerRef" class="sc-wafer-map-perspective" @dblclick="onDblClick">
    <canvas ref="bgRef" class="sc-wafer-map-perspective__bg" />
    <SimplePerspectiveMap
      :points="props.points ?? []"
      :color-map="colorMap ?? {}"
      :zoom="zoom"
      :center-x="centerX"
      :center-y="centerY"
      :data-range-nm="(waferRadiusNm ?? DEFAULT_WAFER_RADIUS_NM) * 2"
      :data-bounds="dataBounds"
    />
    <canvas
      ref="overlayRef"
      class="sc-wafer-map-perspective__overlay"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @contextmenu.prevent
    />
  </div>
</template>

<style scoped>
.sc-wafer-map-perspective {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
}
.sc-wafer-map-perspective__bg {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 0;
}
.sc-wafer-map-perspective__overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  touch-action: none;
}
</style>
