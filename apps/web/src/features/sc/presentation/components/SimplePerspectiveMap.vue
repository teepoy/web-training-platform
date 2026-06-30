<script setup lang="ts">
import { nextTick, onUnmounted, onUpdated, ref, watch } from "vue";

const STRIDE = 6;

const props = defineProps<{
  points: number[] | Float32Array;
  colorMap: Record<string, string>;
  zoom?: { x: number; y: number; w: number; h: number } | null;
  centerX: number;
  centerY: number;
  dataRangeNm: number;
  dataBounds?: { minX: number; maxX: number; minY: number; maxY: number };
}>();

const containerRef = ref<HTMLDivElement | null>(null);
const canvasRef = ref<HTMLCanvasElement | null>(null);

let ptBaseCanvas: HTMLCanvasElement | null = null;
let ptBaseCtx: CanvasRenderingContext2D | null = null;
let ptOverlayCanvas: HTMLCanvasElement | null = null;
let ptOverlayCtx: CanvasRenderingContext2D | null = null;
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

function clearCanvas(canvas: HTMLCanvasElement | null, ctx: CanvasRenderingContext2D | null): void {
  if (!canvas || !ctx) return;
  prepareCanvas(canvas, ctx);
  ctx.clearRect(0, 0, canvasW, canvasH);
}

function renderBase() {
  if (!ptBaseCtx || !ptBaseCanvas) return;
  console.debug("[canvas] SimplePerspectiveMap.renderBase", {
    pointCount: Math.floor(props.points.length / STRIDE),
  });
  clearCanvas(ptBaseCanvas, ptBaseCtx);

  const pts = props.points;
  const count = Math.floor(pts.length / STRIDE);
  if (count === 0) return;

  const ctx = ptBaseCtx;

  // Pass 1 — coloured rects (2x2 fill)
  for (let i = 0, pi = 0; pi < count; i += STRIDE, pi++) {
    ctx.fillStyle = props.colorMap[String(pts[i + 2])] ?? "rgb(255, 0, 0)";
    const [sx, sy] = dataToScreen(pts[i], pts[i + 1]);
    const [cxVal, cyVal] = screenPixel(sx, sy);
    ctx.fillRect(cxVal - 1, cyVal, 2, 2);
  }

  // Pass 2 — has_images black stroke rect (6x6)
  ctx.strokeStyle = "#000000";
  ctx.lineWidth = 1;
  for (let i = 0, pi = 0; pi < count; i += STRIDE, pi++) {
    if (pts[i + 4] === 0) continue;
    const [sx, sy] = dataToScreen(pts[i], pts[i + 1]);
    const [cxVal, cyVal] = screenPixel(sx, sy);
    ctx.strokeRect(cxVal - 3, cyVal - 3, 6, 6);
  }
}

function renderOverlays() {
  if (!ptOverlayCtx || !ptOverlayCanvas) return;
  console.debug("[canvas] SimplePerspectiveMap.renderOverlays", {
    pointCount: Math.floor(props.points.length / STRIDE),
  });
  clearCanvas(ptOverlayCanvas, ptOverlayCtx);

  const pts = props.points;
  const count = Math.floor(pts.length / STRIDE);
  if (count === 0) return;

  const ctx = ptOverlayCtx;

  // Pass 1 — map_in_selection black crosshair (5x5)
  ctx.strokeStyle = "#000000";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let i = 0, pi = 0; pi < count; i += STRIDE, pi++) {
    if (pts[i + 3] === 0) continue;
    const [sx, sy] = dataToScreen(pts[i], pts[i + 1]);
    const [cxVal, cyVal] = screenPixel(sx, sy);
    ctx.moveTo(cxVal - 3, cyVal);
    ctx.lineTo(cxVal + 3, cyVal);
    ctx.moveTo(cxVal, cyVal - 3);
    ctx.lineTo(cxVal, cyVal + 3);
  }
  ctx.stroke();

  // Pass 2 — gallery_in_selection purple crosshair (5x5)
  ctx.strokeStyle = "#A855F7";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let i = 0, pi = 0; pi < count; i += STRIDE, pi++) {
    if (pts[i + 5] === 0) continue;
    const [sx, sy] = dataToScreen(pts[i], pts[i + 1]);
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
  if (ptBaseCanvas)
    ctx.drawImage(
      ptBaseCanvas,
      0,
      0,
      ptBaseCanvas.width,
      ptBaseCanvas.height,
      0,
      0,
      canvasW,
      canvasH,
    );
  if (ptOverlayCanvas)
    ctx.drawImage(
      ptOverlayCanvas,
      0,
      0,
      ptOverlayCanvas.width,
      ptOverlayCanvas.height,
      0,
      0,
      canvasW,
      canvasH,
    );
}

function fullRender() {
  console.debug("[canvas] SimplePerspectiveMap.fullRender");
  recalcTransform();
  renderBase();
  renderOverlays();
  draw();
}

function onResize() {
  fullRender();
}

function initOffscreenCanvases() {
  if (!ptBaseCanvas) {
    ptBaseCanvas = document.createElement("canvas");
    ptBaseCtx = ptBaseCanvas.getContext("2d");
  }
  if (!ptOverlayCanvas) {
    ptOverlayCanvas = document.createElement("canvas");
    ptOverlayCtx = ptOverlayCanvas.getContext("2d");
  }
}

watch(
  containerRef,
  (el) => {
    if (el) {
      initOffscreenCanvases();
      resizeObserver?.disconnect();
      resizeObserver = new ResizeObserver(onResize);
      resizeObserver.observe(el);
      fullRender();
    }
  },
  { immediate: true },
);

// TODO: remove points from this watch once selection flags are split into a separate data channel.
// Currently legend hidden / global filter changes produce a new points array, requiring base re-render.
watch(
  () => [props.points, props.colorMap, props.zoom] as const,
  () => {
    console.debug("[canvas] SimplePerspectiveMap watch points/colorMap/zoom → renderBase");
    void nextTick(() => {
      recalcTransform();
      renderBase();
      draw();
    });
  },
  { immediate: true },
);

watch(
  () => [props.points, props.zoom] as const,
  () => {
    console.debug("[canvas] SimplePerspectiveMap watch points/zoom → renderOverlays");
    void nextTick(() => {
      recalcTransform();
      renderOverlays();
      draw();
    });
  },
  { immediate: true },
);

onUnmounted(() => {
  resizeObserver?.disconnect();
  ptBaseCanvas = null;
  ptBaseCtx = null;
  ptOverlayCanvas = null;
  ptOverlayCtx = null;
});

onUpdated(() => console.debug("[render] SimplePerspectiveMap"));
</script>

<template>
  <div ref="containerRef" style="width: 100%; height: 100%; position: relative">
    <canvas ref="canvasRef" style="width: 100%; height: 100%; display: block" />
  </div>
</template>
