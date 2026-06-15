<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import type { SimpleMapPoint } from "./SimpleMapPoint";

const props = defineProps<{
  points: SimpleMapPoint[];
  colorMap: Record<string, string>;
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
  if (props.zoom) {
    const z = props.zoom;
    return { minX: z.x, maxX: z.x + z.w, minY: z.y, maxY: z.y + z.h };
  }
  const dieSizeX = Math.max(0, props.dieSizeX ?? 0);
  const dieSizeY = Math.max(0, props.dieSizeY ?? 0);
  if (pts.length === 0 && dieSizeX === 0 && dieSizeY === 0) return;
  let minX = 0,
    maxX = dieSizeX,
    minY = 0,
    maxY = dieSizeY;
  for (const p of pts) {
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.y > maxY) maxY = p.y;
  }
  if (minX === maxX) {
    minX -= 0.5;
    maxX += 0.5;
  }
  if (minY === maxY) {
    minY -= 0.5;
    maxY += 0.5;
  }
  return { minX, maxX, minY, maxY };
}

function recalcTransform(bounds?: { minX: number; maxX: number; minY: number; maxY: number }) {
  if (!containerRef.value) return;
  canvasW = containerRef.value.clientWidth || 1;
  canvasH = containerRef.value.clientHeight || 1;
  cx = canvasW / 2;
  cy = canvasH / 2;

  if (bounds) {
    const spanX = bounds.maxX - bounds.minX;
    const spanY = bounds.maxY - bounds.minY;
    const padding = props.zoom ? 1.0 : 0.9;
    scale = Math.min((canvasW * padding) / spanX, (canvasH * padding) / spanY);
    if (!Number.isFinite(scale) || scale === 0) scale = 1;
    offsetX = -(bounds.minX + bounds.maxX) / 2;
    offsetY = -(bounds.minY + bounds.maxY) / 2;
  } else {
    scale = 1;
    offsetX = 0;
    offsetY = 0;
  }
}

function dataToScreen(x: number, y: number): [number, number] {
  return [cx + (x + offsetX) * scale, cy - (y + offsetY) * scale];
}

function renderBackground() {
  if (!bgCtx || !bgCanvas) return;
  prepareCanvas(bgCanvas, bgCtx);
  bgCtx.clearRect(0, 0, canvasW, canvasH);
  bgCtx.fillStyle = "#ffffff";
  bgCtx.fillRect(0, 0, canvasW, canvasH);
  const dieSizeX = Math.max(0, props.dieSizeX ?? 0);
  const dieSizeY = Math.max(0, props.dieSizeY ?? 0);
  if (dieSizeX > 0 && dieSizeY > 0) {
    const [left, bottom] = dataToScreen(0, 0);
    const [right, top] = dataToScreen(dieSizeX, dieSizeY);
    bgCtx.strokeStyle = "#9ca3af";
    bgCtx.lineWidth = 1;
    bgCtx.strokeRect(left, top, right - left, bottom - top);
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
  const bounds = computeBounds(props.points);
  recalcTransform(bounds);
  renderBackground();
  renderPoints();
  draw();
}

function onResize() {
  const bounds = computeBounds(props.points);
  recalcTransform(bounds);
  renderBackground();
  renderPoints();
  draw();
}

function scheduleFullRender() {
  void nextTick(() => {
    fullRender();
    window.requestAnimationFrame(fullRender);
  });
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

watch(() => [props.zoom, props.dieSizeX, props.dieSizeY], scheduleFullRender, { deep: true });

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
  <div class="sdsm">
    <div ref="containerRef" class="sdsm-chart">
      <canvas ref="canvasRef" class="sdsm-canvas" />
    </div>
  </div>
</template>

<style scoped>
.sdsm {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.sdsm-empty {
  font-size: 12px;
  color: #888;
  padding: 12px 0;
  text-align: center;
}

.sdsm-chart {
  position: relative;
  width: 100%;
  flex: 1 1 0;
  min-height: 0;
  background: #ffffff;
  border-radius: 4px;
  overflow: hidden;
}

.sdsm-canvas {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
