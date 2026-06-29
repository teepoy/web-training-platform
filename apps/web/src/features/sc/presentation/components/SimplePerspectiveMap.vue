<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from "vue";
import type { PerspectiveMapPoint } from "./SimpleMapPoint";

const props = defineProps<{
  points: PerspectiveMapPoint[];
  colorMap: Record<string, string>;
  zoom?: { x: number; y: number; w: number; h: number } | null;
  centerX: number;
  centerY: number;
  dataRangeNm: number;
  dataBounds?: { minX: number; maxX: number; minY: number; maxY: number };
}>();

const containerRef = ref<HTMLDivElement | null>(null);
const canvasRef = ref<HTMLCanvasElement | null>(null);

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
  } else if (props.dataBounds) {
    const b = props.dataBounds;
    const spanX = b.maxX - b.minX || 1;
    const spanY = b.maxY - b.minY || 1;
    scale = Math.min(canvasW / spanX, canvasH / spanY);
    offsetX = -(b.minX + b.maxX) / 2;
    offsetY = -(b.minY + b.maxY) / 2;
  } else {
    const range = props.dataRangeNm;
    scale = Math.min(canvasW, canvasH) / range;
    offsetX = -props.centerX;
    offsetY = -props.centerY;
  }
}

function dataToScreen(x: number, y: number): [number, number] {
  return [cx + (x + offsetX) * scale, cy - (y + offsetY) * scale];
}

function renderPoints() {
  if (!ptCtx || !ptCanvas) return;
  const ctx = ptCtx;
  prepareCanvas(ptCanvas, ctx);
  ctx.clearRect(0, 0, canvasW, canvasH);

  const pts = props.points;
  if (pts.length === 0) return;

  const groups = new Map<string, PerspectiveMapPoint[]>();
  for (const p of pts) {
    const arr = groups.get(p.label);
    if (arr) arr.push(p);
    else groups.set(p.label, [p]);
  }

  // ── Pass 1 ── defect coloured rects: 2x2 fill by class
  const sortedGroups = Array.from(groups.entries()).sort(([left], [right]) =>
    left.localeCompare(right, undefined, { numeric: true }),
  );
  for (const [label, group] of sortedGroups) {
    ctx.fillStyle = props.colorMap[label] ?? "rgb(255, 0, 0)";
    ctx.beginPath();
    for (const p of group) {
      const [sx, sy] = dataToScreen(p.x, p.y);
      const [cxVal, cyVal] = screenPixel(sx, sy);
      ctx.rect(cxVal - 1, cyVal, 2, 2);
    }
    ctx.fill();
  }

  // ── Pass 2 ── map_in_selection: 5x5 black crosshair
  ctx.strokeStyle = "#000000";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (const p of pts) {
    if (!p.mapInSelection) continue;
    const [sx, sy] = dataToScreen(p.x, p.y);
    const [cxVal, cyVal] = screenPixel(sx, sy);
    ctx.moveTo(cxVal - 3, cyVal);
    ctx.lineTo(cxVal + 3, cyVal);
    ctx.moveTo(cxVal, cyVal - 3);
    ctx.lineTo(cxVal, cyVal + 3);
  }
  ctx.stroke();

  // ── Pass 3 ── has_images: 6x6 black stroke rect
  ctx.strokeStyle = "#000000";
  ctx.lineWidth = 1;
  for (const p of pts) {
    if (!p.hasImages) continue;
    const [sx, sy] = dataToScreen(p.x, p.y);
    const [cxVal, cyVal] = screenPixel(sx, sy);
    ctx.strokeRect(cxVal - 3, cyVal - 3, 6, 6);
  }

  // ── Pass 4 ── gallery_in_selection: 5x5 purple crosshair
  ctx.strokeStyle = "#A855F7";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (const p of pts) {
    if (!p.galleryInSelection) continue;
    const [sx, sy] = dataToScreen(p.x, p.y);
    const [cxVal, cyVal] = screenPixel(sx, sy);
    ctx.moveTo(cxVal - 3, cyVal);
    ctx.lineTo(cxVal + 3, cyVal);
    ctx.moveTo(cxVal, cyVal - 3);
    ctx.lineTo(cxVal, cyVal + 3);
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
  if (ptCanvas)
    ctx.drawImage(ptCanvas, 0, 0, ptCanvas.width, ptCanvas.height, 0, 0, canvasW, canvasH);
}

function fullRender() {
  recalcTransform();
  renderPoints();
  draw();
}

function onResize() {
  fullRender();
}

watch(
  containerRef,
  (el) => {
    if (el) {
      if (!ptCanvas) {
        ptCanvas = document.createElement("canvas");
        ptCtx = ptCanvas.getContext("2d");
      }
      resizeObserver?.disconnect();
      resizeObserver = new ResizeObserver(onResize);
      resizeObserver.observe(el);
      fullRender();
    }
  },
  { immediate: true },
);

watch(
  () => [props.points, props.colorMap, props.zoom],
  () => {
    void nextTick(fullRender);
  },
  { deep: true },
);

onUnmounted(() => {
  resizeObserver?.disconnect();
  ptCanvas = null;
  ptCtx = null;
});
</script>

<template>
  <div
    ref="containerRef"
    style="width: 100%; height: 100%; position: relative; background: #e8e8e8"
  >
    <canvas ref="canvasRef" style="width: 100%; height: 100%; display: block" />
  </div>
</template>
