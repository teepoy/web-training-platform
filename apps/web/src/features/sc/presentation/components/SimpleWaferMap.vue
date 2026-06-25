<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import type { SimpleMapPoint } from "./SimpleMapPoint";

const DEFAULT_WAFER_RADIUS_NM = 150_000_000;
const DEFAULT_DIE_SIZE_X = 8_000_000;
const DEFAULT_DIE_SIZE_Y = 5_000_000;
const DIE_LINE_COLOR = "#9ca3af";
const WAFER_EDGE_COLOR = "#333333";

const props = defineProps<{
  points: SimpleMapPoint[];
  colorMap: Record<string, string>;
  /** Viewport in data coords: { x, y, w, h }. When set, only this region is rendered. Grid/border adapt; point size stays fixed. */
  zoom?: { x: number; y: number; w: number; h: number } | null;
  /** Wafer center X coordinate (nm). Default 0. */
  centerX?: number;
  /** Wafer center Y coordinate (nm). Default 0. */
  centerY?: number;
  /** Die width (nm). Default 8_000_000. */
  dieSizeX?: number;
  /** Die height (nm). Default 5_000_000. */
  dieSizeY?: number;
  /** Die grid origin X coordinate (nm). Defaults to centerX for backward compat. */
  originX?: number;
  /** Die grid origin Y coordinate (nm). Defaults to centerY for backward compat. */
  originY?: number;
}>();

const containerRef = ref<HTMLDivElement | null>(null);
const canvasRef = ref<HTMLCanvasElement | null>(null);

const pointsCount = ref(0);

let bgCanvas: HTMLCanvasElement | null = null;
let bgCtx: CanvasRenderingContext2D | null = null;
let ptCanvas: HTMLCanvasElement | null = null;
let ptCtx: CanvasRenderingContext2D | null = null;
let resizeObserver: ResizeObserver | null = null;

let canvasW = 600;
let canvasH = 600;
let cx = 300;
let cy = 300;
let scale = 1;
let offsetX = 0;
let offsetY = 0;

const waferRadiusNm = DEFAULT_WAFER_RADIUS_NM;
const dieSizeX = computed(() => props.dieSizeX ?? DEFAULT_DIE_SIZE_X);
const dieSizeY = computed(() => props.dieSizeY ?? DEFAULT_DIE_SIZE_Y);
const centerX = computed(() => props.centerX ?? 0);
const centerY = computed(() => props.centerY ?? 0);
const originX = computed(() => props.originX ?? centerX.value);
const originY = computed(() => props.originY ?? centerY.value);

let dieGridData: { x: number; y: number; valid: boolean }[] = [];
let gridExtent = 0;

function canvasPixelRatio(): number {
  return typeof window === "undefined" ? 1 : window.devicePixelRatio || 1;
}

function prepareCanvas(canvas: HTMLCanvasElement, ctx: CanvasRenderingContext2D): void {
  const dpr = canvasPixelRatio();
  const width = Math.max(1, Math.round(canvasW * dpr));
  const height = Math.max(1, Math.round(canvasH * dpr));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.imageSmoothingEnabled = false;
}

function screenPixel(x: number, y: number): [number, number] {
  return [Math.round(x), Math.round(y)];
}

function buildDieGrid() {
  dieGridData = [];
  const dw = Math.max(1, dieSizeX.value);
  const dh = Math.max(1, dieSizeY.value);

  const screenDieW = dw * scale;
  const screenDieH = dh * scale;
  if (screenDieW < 0.5 && screenDieH < 0.5) return;

  const z = props.zoom;
  const minX = z ? z.x : centerX.value - waferRadiusNm;
  const maxX = z ? z.x + z.w : centerX.value + waferRadiusNm;
  const minY = z ? z.y : centerY.value - waferRadiusNm;
  const maxY = z ? z.y + z.h : centerY.value + waferRadiusNm;

  const ixStart = Math.floor((minX - originX.value) / dw) - 1;
  const ixEnd = Math.ceil((maxX - originX.value) / dw) + 1;
  const iyStart = Math.floor((minY - originY.value) / dh) - 1;
  const iyEnd = Math.ceil((maxY - originY.value) / dh) + 1;

  gridExtent = Math.max(Math.abs(ixStart), Math.abs(ixEnd), Math.abs(iyStart), Math.abs(iyEnd));

  const totalCells = (ixEnd - ixStart + 1) * (iyEnd - iyStart + 1);
  if (totalCells > 50_000) return;

  const r = waferRadiusNm;
  for (let ix = ixStart; ix <= ixEnd; ix++) {
    for (let iy = iyStart; iy <= iyEnd; iy++) {
      const left = originX.value + ix * dw;
      const top = originY.value + iy * dh;
      const right = left + dw;
      const bottom = top + dh;

      // Skip dies fully outside zoom viewport
      if (z && (right < z.x || left > z.x + z.w || bottom < z.y || top > z.y + z.h)) continue;

      const clampX = Math.max(left, Math.min(centerX.value, right));
      const clampY = Math.max(top, Math.min(centerY.value, bottom));
      const distToCenter = Math.hypot(clampX - centerX.value, clampY - centerY.value);
      if (distToCenter > r) continue;

      const d1 = Math.hypot(left - centerX.value, top - centerY.value);
      const d2 = Math.hypot(right - centerX.value, top - centerY.value);
      const d3 = Math.hypot(left - centerX.value, bottom - centerY.value);
      const d4 = Math.hypot(right - centerX.value, bottom - centerY.value);
      const maxDist = Math.max(d1, d2, d3, d4);

      dieGridData.push({ x: left, y: top, valid: maxDist <= r });
    }
  }
}

function recalcTransform() {
  if (!containerRef.value) return;
  canvasW = containerRef.value.clientWidth || 1;
  canvasH = containerRef.value.clientHeight || 1;
  cx = canvasW / 2;
  cy = canvasH / 2;

  if (props.zoom) {
    const z = props.zoom;
    const scaleX = canvasW / z.w;
    const scaleY = canvasH / z.h;
    scale = Math.min(scaleX, scaleY);
    offsetX = -(z.x + z.w / 2);
    offsetY = -(z.y + z.h / 2);
  } else {
    scale = Math.min(canvasW, canvasH) / (2 * waferRadiusNm);
    offsetX = -centerX.value;
    offsetY = -centerY.value;
  }

  const viewMinX = -cx / scale - offsetX;
  const viewMaxX = (canvasW - cx) / scale - offsetX;
  const viewMinY = -(canvasH - cy) / scale - offsetY;
  const viewMaxY = cy / scale - offsetY;
}

function dataToScreen(x: number, y: number): [number, number] {
  return [cx + (x + offsetX) * scale, cy - (y + offsetY) * scale];
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
  if (!bgCtx || !bgCanvas) return;
  const ctx = bgCtx;
  prepareCanvas(bgCanvas, ctx);
  ctx.clearRect(0, 0, canvasW, canvasH);

  const z = props.zoom;
  const zMinX = z ? z.x : centerX.value - waferRadiusNm;
  const zMaxX = z ? z.x + z.w : centerX.value + waferRadiusNm;
  const zMinY = z ? z.y : centerY.value - waferRadiusNm;
  const zMaxY = z ? z.y + z.h : centerY.value + waferRadiusNm;

  if (z) {
    // Zoomed — plain background + dies + grid + border, no wafer outline
    ctx.fillStyle = "#e8e8e8";
    ctx.fillRect(0, 0, canvasW, canvasH);

    for (const die of dieGridData) {
      const [dx, dy] = dataToScreen(die.x, die.y);
      const dw = dieSizeX.value * scale;
      const dh = dieSizeY.value * scale;
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

    const ixMin = Math.floor((zMinX - originX.value) / dieSizeX.value);
    const ixMax = Math.ceil((zMaxX - originX.value) / dieSizeX.value);
    const iyMin = Math.floor((zMinY - originY.value) / dieSizeY.value);
    const iyMax = Math.ceil((zMaxY - originY.value) / dieSizeY.value);

    for (let ix = ixMin; ix <= ixMax + 1; ix++) {
      const dataX = originX.value + ix * dieSizeX.value;
      const [sx] = dataToScreen(dataX, 0);
      const [, sy1] = dataToScreen(0, zMinY);
      const [, sy2] = dataToScreen(0, zMaxY);
      ctx.moveTo(Math.round(sx) + 0.5, sy1);
      ctx.lineTo(Math.round(sx) + 0.5, sy2);
    }
    for (let iy = iyMin; iy <= iyMax + 1; iy++) {
      const dataY = originY.value + iy * dieSizeY.value;
      const [sx1] = dataToScreen(zMinX, 0);
      const [sx2] = dataToScreen(zMaxX, 0);
      const [, sy] = dataToScreen(0, dataY);
      ctx.moveTo(sx1, Math.round(sy) + 0.5);
      ctx.lineTo(sx2, Math.round(sy) + 0.5);
    }
    ctx.stroke();

    ctx.strokeStyle = WAFER_EDGE_COLOR;
    ctx.lineWidth = 2;
    ctx.strokeRect(1, 1, canvasW - 2, canvasH - 2);
  } else {
    // Full wafer — wafer path with notch
    const [ex, ey] = dataToScreen(centerX.value, centerY.value);
    const r = waferRadiusNm * scale;

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
    ctx.fillRect(0, 0, canvasW, canvasH);

    for (const die of dieGridData) {
      const [dx, dy] = dataToScreen(die.x, die.y);
      const dw = dieSizeX.value * scale;
      const dh = dieSizeY.value * scale;
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
      const dataX = originX.value + ix * dieSizeX.value;
      const [sx] = dataToScreen(dataX, 0);
      const [, sy1] = dataToScreen(0, zMinY);
      const [, sy2] = dataToScreen(0, zMaxY);
      ctx.moveTo(Math.round(sx) + 0.5, sy1);
      ctx.lineTo(Math.round(sx) + 0.5, sy2);
    }
    for (let iy = -gridExtent; iy <= gridExtent + 1; iy++) {
      const dataY = originY.value + iy * dieSizeY.value;
      const [sx1] = dataToScreen(zMinX, 0);
      const [sx2] = dataToScreen(zMaxX, 0);
      const [, sy] = dataToScreen(0, dataY);
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

function renderPoints() {
  if (!ptCtx || !ptCanvas) return;
  const ctx = ptCtx;
  prepareCanvas(ptCanvas, ctx);
  ctx.clearRect(0, 0, canvasW, canvasH);

  const pts = props.points;
  if (pts.length === 0) return;

  const groups = new Map<string, SimpleMapPoint[]>();
  for (const p of pts) {
    const arr = groups.get(p.label);
    if (arr) arr.push(p);
    else groups.set(p.label, [p]);
  }

  // Pass 1 — defect pixels: exactly (wx - 1, wy), (wx, wy), (wx - 1, wy + 1), (wx, wy + 1).
  const sortedGroups = Array.from(groups.entries()).sort(([left], [right]) =>
    left.localeCompare(right, undefined, { numeric: true }),
  );
  for (const [label, group] of sortedGroups) {
    ctx.fillStyle = props.colorMap[label] ?? "rgb(255, 0, 0)";
    ctx.beginPath();
    for (const p of group) {
      const [sx, sy] = dataToScreen(p.x, p.y);
      const [cx, cy] = screenPixel(sx, sy);
      ctx.rect(cx - 1, cy, 2, 2);
    }
    ctx.fill();
  }

  // Pass 2 — image flag box above defect pixels.
  ctx.strokeStyle = "#000000";
  ctx.lineWidth = 1;
  for (const p of pts) {
    if (!p.hasImageFlag) continue;
    const [sx, sy] = dataToScreen(p.x, p.y);
    const [cx, cy] = screenPixel(sx, sy);
    ctx.strokeRect(cx - 3, cy - 2, 5, 5);
  }

  // Pass 3 — selected crosshair above all point markers.
  ctx.strokeStyle = "#000000";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (const p of pts) {
    if (!p.isSelectedFlag) continue;
    const [sx, sy] = dataToScreen(p.x, p.y);
    const [cx, cy] = screenPixel(sx, sy);
    ctx.moveTo(cx - 3, cy);
    ctx.lineTo(cx + 3, cy);
    ctx.moveTo(cx, cy - 3);
    ctx.lineTo(cx, cy + 3);
  }
  ctx.stroke();
}

function draw() {
  const canvas = canvasRef.value;
  if (!canvas || canvasW <= 0 || canvasH <= 0) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  prepareCanvas(canvas, ctx);
  ctx.clearRect(0, 0, canvasW, canvasH);
  if (bgCanvas)
    ctx.drawImage(bgCanvas, 0, 0, bgCanvas.width, bgCanvas.height, 0, 0, canvasW, canvasH);
  if (ptCanvas)
    ctx.drawImage(ptCanvas, 0, 0, ptCanvas.width, ptCanvas.height, 0, 0, canvasW, canvasH);
}

function fullRender() {
  recalcTransform();

  const pts = props.points;
  if (pts.length > 0) {
    let minX = Infinity,
      maxX = -Infinity,
      minY = Infinity,
      maxY = -Infinity;
    for (const p of pts) {
      if (p.x < minX) minX = p.x;
      if (p.x > maxX) maxX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.y > maxY) maxY = p.y;
    }
  }

  renderBackground();
  renderPoints();
  draw();
}

function onResize() {
  recalcTransform();
  renderBackground();
  renderPoints();
  draw();
}

watch(
  () => props.points,
  async (pts) => {
    pointsCount.value = pts.length;

    await nextTick();

    if (containerRef.value && !resizeObserver) {
      resizeObserver = new ResizeObserver(onResize);
      resizeObserver.observe(containerRef.value);
    }

    fullRender();
  },
  { immediate: true },
);

watch(
  () => props.colorMap,
  () => {
    renderPoints();
    draw();
  },
);

watch(
  () => props.zoom,
  () => {
    recalcTransform();
    buildDieGrid();
    renderBackground();
    renderPoints();
    draw();
  },
);

onMounted(() => {
  bgCanvas = document.createElement("canvas");
  bgCtx = bgCanvas.getContext("2d");
  ptCanvas = document.createElement("canvas");
  ptCtx = ptCanvas.getContext("2d");

  buildDieGrid();

  if (containerRef.value) {
    resizeObserver = new ResizeObserver(onResize);
    resizeObserver.observe(containerRef.value);
  }

  fullRender();
});

onUnmounted(() => {
  resizeObserver?.disconnect();
  resizeObserver = null;
  bgCanvas = null;
  bgCtx = null;
  ptCanvas = null;
  ptCtx = null;
});
</script>

<template>
  <div class="swm">
    <div ref="containerRef" class="swm-chart">
      <canvas ref="canvasRef" class="swm-canvas" />
    </div>
  </div>
</template>

<style scoped>
.swm {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.swm-empty-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #e8e8e8;
  font-size: 12px;
  color: #888;
  z-index: 10;
}

.swm-chart {
  position: relative;
  width: 100%;
  flex: 1 1 0;
  min-height: 0;
  background: #e8e8e8;
  border-radius: 4px;
  overflow: hidden;
}

.swm-canvas {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
