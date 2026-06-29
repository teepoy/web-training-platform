<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import SimplePerspectiveMap from "./SimplePerspectiveMap.vue";
import type { PerspectiveMapPoint } from "./SimpleMapPoint";
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
const DEFAULT_RET_RANGE = 400_000;

const props = defineProps<{
  points?: MapDisplayArray | number[];
  xDieCount?: number;
  yDieCount?: number;
  dieSizeX?: number;
  dieSizeY?: number;
  colorMap?: Record<string, string>;
  zoom?: { x: number; y: number; w: number; h: number } | null;
  mode?: "select" | "zoomin";
  queryBoxSelection?: (region: { x: number; y: number; w: number; h: number }) => Promise<number[]>;
  highlightDefects?: HighlightDefect[];
}>();

function resolveGridW(): number {
  const cols = props.xDieCount ?? 0;
  const dsx = props.dieSizeX ?? 0;
  return cols > 0 && dsx > 0 ? cols * dsx : DEFAULT_RET_RANGE;
}

function resolveGridH(): number {
  const rows = props.yDieCount ?? 0;
  const dsy = props.dieSizeY ?? 0;
  return rows > 0 && dsy > 0 ? rows * dsy : DEFAULT_RET_RANGE;
}

const dataBounds = computed(() => ({
  minX: 0,
  maxX: resolveGridW(),
  minY: 0,
  maxY: resolveGridH(),
}));

const emit = defineEmits<{
  (e: "selection-change", ids: number[]): void;
  (e: "zoom-in", viewport: { x: number; y: number; w: number; h: number } | null): void;
  (e: "box-select", region: { x: number; y: number; w: number; h: number }): void;
}>();

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
    minX: 0,
    maxX: DEFAULT_RET_RANGE,
    minY: 0,
    maxY: DEFAULT_RET_RANGE,
  },
  1,
);

const centerX = computed(() => resolveGridW() / 2);
const centerY = computed(() => resolveGridH() / 2);

const perspectivePoints = computed<PerspectiveMapPoint[]>(() => {
  const pts = props.points;
  if (!pts || pts.length === 0) return [];
  const count = Math.floor(pts.length / STRIDE);
  const result: PerspectiveMapPoint[] = new Array(count);
  for (let i = 0, pi = 0; pi < count; i += STRIDE, pi++) {
    result[pi] = {
      x: pts[i],
      y: pts[i + 1],
      label: String(pts[i + 2]),
      mapInSelection: pts[i + 3] !== 0,
      hasImages: pts[i + 4] !== 0,
      galleryInSelection: pts[i + 5] !== 0,
    };
  }
  return result;
});

function recalcTransform() {
  const size = measureMapElement(containerRef.value);
  if (!size) return;
  mapSize = size;
  if (props.zoom) {
    transform = buildMapTransform(mapSize, boundsFromRegion(props.zoom), 1.0);
  } else {
    const b = dataBounds.value;
    transform = buildMapTransform(
      mapSize,
      { minX: b.minX, maxX: b.maxX, minY: b.minY, maxY: b.maxY },
      1,
    );
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
  immediateCrosshairPoints.value = [];
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
  if (mode.value === "zoomin") emit("zoom-in", region);
  else {
    const inRegion = perspectivePoints.value.filter(
      (p) =>
        p.x >= region.x &&
        p.x <= region.x + region.w &&
        p.y >= region.y &&
        p.y <= region.y + region.h,
    );
    immediateCrosshairPoints.value = inRegion.map((p) => ({ x: p.x, y: p.y }));
    console.debug("[ScReticleMapPerspective] immediateCrosshair", {
      count: inRegion.length,
      region,
    });
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
  if (mode.value === "zoomin" && props.zoom) emit("zoom-in", null);
  else if (mode.value === "select") emit("selection-change", []);
}

function drawOverlay() {
  const cvs = overlayRef.value;
  if (!cvs || mapSize.width <= 0 || mapSize.height <= 0) return;
  const ctx = prepareOverlayCanvas(cvs, mapSize);
  if (!ctx) return;

  if (props.highlightDefects && props.highlightDefects.length > 0) {
    ctx.fillStyle = HIGHLIGHT_POINT_COLOR;
    for (const hd of props.highlightDefects) {
      const [sx, sy] = dataToScreen(transform, hd.reticleX, hd.reticleY);
      ctx.fillRect(sx - 1.5, sy - 1.5, 3, 3);
    }
  }

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

function renderBackground() {
  const cvs = bgRef.value;
  if (!cvs || mapSize.width <= 0 || mapSize.height <= 0) return;
  const ctx = prepareOverlayCanvas(cvs, mapSize);
  if (!ctx) return;

  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, mapSize.width, mapSize.height);

  const b = dataBounds.value;
  const [minSx, maxSy] = dataToScreen(transform, b.minX, b.minY);
  const [maxSx, minSy] = dataToScreen(transform, b.maxX, b.maxY);

  const cols = props.xDieCount ?? 0;
  const rows = props.yDieCount ?? 0;
  const dsx = props.dieSizeX ?? 0;
  const dsy = props.dieSizeY ?? 0;

  ctx.strokeStyle = "rgba(195, 200, 208, 0.7)";
  ctx.lineWidth = 1;
  ctx.beginPath();

  if (cols > 0 && dsx > 0) {
    for (let i = 0; i <= cols; i++) {
      const x = i * dsx;
      const [sx] = dataToScreen(transform, x, 0);
      ctx.moveTo(sx, minSy);
      ctx.lineTo(sx, maxSy);
    }
  }
  if (rows > 0 && dsy > 0) {
    for (let i = 0; i <= rows; i++) {
      const y = i * dsy;
      const [, sy] = dataToScreen(transform, 0, y);
      ctx.moveTo(minSx, sy);
      ctx.lineTo(maxSx, sy);
    }
  }
  ctx.stroke();
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
    recalcTransform();
    if (immediateCrosshairPoints.value.length > 0) {
      immediateCrosshairPoints.value = [];
    }
    drawOverlay();
  },
);
watch(
  () => props.mode,
  () => {
    if (immediateCrosshairPoints.value.length > 0) {
      immediateCrosshairPoints.value = [];
      drawOverlay();
    }
  },
);
</script>

<template>
  <div ref="containerRef" class="sc-reticle-map-perspective" @dblclick="onDblClick">
    <canvas ref="bgRef" class="sc-reticle-map-perspective__bg" />
    <SimplePerspectiveMap
      :points="perspectivePoints"
      :color-map="colorMap ?? {}"
      :zoom="zoom"
      :center-x="centerX"
      :center-y="centerY"
      :data-range-nm="DEFAULT_RET_RANGE"
      :data-bounds="dataBounds"
    />
    <canvas
      ref="overlayRef"
      class="sc-reticle-map-perspective__overlay"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @contextmenu.prevent
    />
  </div>
</template>

<style scoped>
.sc-reticle-map-perspective {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
}
.sc-reticle-map-perspective__bg {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 0;
}
.sc-reticle-map-perspective__overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  touch-action: none;
}
</style>
