<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from "vue";
import type { SimpleMapPoint } from "./SimpleMapPoint";

const DEFAULT_DIE_COUNT = 10;

const props = defineProps<{
  points: SimpleMapPoint[];
  colorMap: Record<string, string>;
  xDieCount?: number;
  yDieCount?: number;
  dieSizeX?: number;
  dieSizeY?: number;
  zoom?: { x: number; y: number; w: number; h: number } | null;
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
let canvasH = 240;
let cx = 300;
let cy = 120;
let scale = 1;
let offsetX = 0;
let offsetY = 0;

let gridCols = DEFAULT_DIE_COUNT;
let gridRows = DEFAULT_DIE_COUNT;
let dieSizeXNum = 1;
let dieSizeYNum = 1;
let boundsMinX = 0;
let boundsMaxX = 1;
let boundsMinY = 0;
let boundsMaxY = 1;

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

function computeBounds(pts: SimpleMapPoint[]) {
  gridCols = Math.max(1, Math.floor(props.xDieCount ?? DEFAULT_DIE_COUNT));
  gridRows = Math.max(1, Math.floor(props.yDieCount ?? DEFAULT_DIE_COUNT));
  dieSizeXNum = Math.max(1, props.dieSizeX ?? 1);
  dieSizeYNum = Math.max(1, props.dieSizeY ?? 1);

  if (props.zoom) {
    const z = props.zoom;
    boundsMinX = z.x;
    boundsMaxX = z.x + z.w;
    boundsMinY = z.y;
    boundsMaxY = z.y + z.h;
    return;
  }

  boundsMinX = 0;
  boundsMaxX = gridCols * dieSizeXNum;
  boundsMinY = 0;
  boundsMaxY = gridRows * dieSizeYNum;

  if (pts.length === 0) return;

  let minX = boundsMinX,
    maxX = boundsMaxX,
    minY = boundsMinY,
    maxY = boundsMaxY;
  for (const p of pts) {
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.y > maxY) maxY = p.y;
  }
  boundsMinX = minX;
  boundsMaxX = maxX;
  boundsMinY = minY;
  boundsMaxY = maxY;
}

function recalcTransform() {
  if (!containerRef.value) return;
  canvasW = containerRef.value.clientWidth || 1;
  canvasH = containerRef.value.clientHeight || 1;
  cx = canvasW / 2;
  cy = canvasH / 2;

  const spanX = boundsMaxX - boundsMinX || 1;
  const spanY = boundsMaxY - boundsMinY || 1;
  scale = Math.min((canvasW * 0.9) / spanX, (canvasH * 0.9) / spanY);
  if (!Number.isFinite(scale) || scale === 0) scale = 1;
  offsetX = -(boundsMinX + boundsMaxX) / 2;
  offsetY = -(boundsMinY + boundsMaxY) / 2;
}

function dataToScreen(x: number, y: number): [number, number] {
  return [cx + (x + offsetX) * scale, cy - (y + offsetY) * scale];
}

function renderBackground() {
  if (!bgCtx || !bgCanvas) return;
  const ctx = bgCtx;
  prepareCanvas(bgCanvas, ctx);
  ctx.clearRect(0, 0, canvasW, canvasH);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvasW, canvasH);

  const [minSx, maxSy] = dataToScreen(boundsMinX, boundsMinY);
  const [maxSx, minSy] = dataToScreen(boundsMaxX, boundsMaxY);

  ctx.strokeStyle = "rgba(195, 200, 208, 0.7)";
  ctx.lineWidth = 1;
  ctx.beginPath();

  if (dieSizeXNum > 0 && dieSizeYNum > 0) {
    for (let i = 0; i <= gridCols; i++) {
      const x = boundsMinX + i * dieSizeXNum;
      const [sx] = dataToScreen(x, 0);
      ctx.moveTo(sx, minSy);
      ctx.lineTo(sx, maxSy);
    }
    for (let i = 0; i <= gridRows; i++) {
      const y = boundsMinY + i * dieSizeYNum;
      const [, sy] = dataToScreen(0, y);
      ctx.moveTo(minSx, sy);
      ctx.lineTo(maxSx, sy);
    }
  }
  ctx.stroke();
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
  computeBounds(props.points);
  recalcTransform();
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
  (pts) => {
    pointsCount.value = pts.length;
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
  () => [props.zoom, props.xDieCount, props.yDieCount, props.dieSizeX, props.dieSizeY],
  () => {
    fullRender();
  },
  { deep: true },
);

onMounted(() => {
  bgCanvas = document.createElement("canvas");
  bgCtx = bgCanvas.getContext("2d");
  ptCanvas = document.createElement("canvas");
  ptCtx = ptCanvas.getContext("2d");

  if (containerRef.value) {
    resizeObserver = new ResizeObserver(onResize);
    resizeObserver.observe(containerRef.value);
  }
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
  <div class="srm">
    <div ref="containerRef" class="srm-chart">
      <canvas ref="canvasRef" class="srm-canvas" />
    </div>
  </div>
</template>

<style scoped>
.srm {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.srm-empty {
  font-size: 12px;
  color: #888;
  padding: 12px 0;
  text-align: center;
}

.srm-chart {
  position: relative;
  width: 100%;
  flex: 1 1 0;
  min-height: 0;
  background: #ffffff;
  border-radius: 4px;
  overflow: hidden;
}

.srm-canvas {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
