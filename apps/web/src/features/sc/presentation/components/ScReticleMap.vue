<!--
  ScReticleMap — Wrapper around SimpleReticleMap with selection / zoom-in mode.
-->
<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import SimpleReticleMap from "./SimpleReticleMap.vue";
import type { SimpleMapPoint } from "./SimpleMapPoint";
import type { HighlightDefect } from "./types";
import { getPackedPointIdsInRegion, STRIDE } from "./scMapUtils";
import {
  boundsFromRegion,
  buildMapTransform,
  constrainDragToAspect,
  dataToScreen,
  eventToLocalPoint,
  measureMapElement,
  normalizeBounds,
  prepareOverlayCanvas,
  screenToData,
  type ScMapBounds,
  type ScMapSize,
  type ScMapTransform,
} from "./scMapViewport";

const HIGHLIGHT_POINT_COLOR = "#A855F7";

const props = defineProps<{
  xDieCount: number;
  yDieCount: number;
  dieSizeX: number;
  dieSizeY: number;
  points?: number[];
  selectedIds?: Set<number>;
  highlightDefects?: HighlightDefect[];
  colorMap?: Record<string, string>;
  zoom?: { x: number; y: number; w: number; h: number } | null;
  mode?: "select" | "zoomin";
  queryBoxSelection?: (region: { x: number; y: number; w: number; h: number }) => Promise<number[]>;
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
const pointCount = computed(() => Math.floor((props.points?.length ?? 0) / STRIDE));

const simplePoints = computed<SimpleMapPoint[]>(() => {
  const pts = props.points;
  if (!pts || pts.length === 0) return [];
  const count = Math.floor(pts.length / STRIDE);
  const result: SimpleMapPoint[] = new Array(count);
  for (let i = 0, pi = 0; pi < count; i += STRIDE, pi++) {
    const defectId = pts[i + 2];
    result[pi] = {
      x: pts[i],
      y: pts[i + 1],
      id: defectId,
      label: String(pts[i + 3]),
      hasImageFlag: pts[i + 5] !== 0,
      isSelectedFlag: selectionState.value.has(defectId),
    };
  }
  return result;
});

// Transform
let mapSize: ScMapSize = { width: 600, height: 240 };
let transform: ScMapTransform = buildMapTransform(
  mapSize,
  { minX: 0, maxX: 1, minY: 0, maxY: 1 },
  0.9,
);

function currentBounds(): ScMapBounds {
  if (props.zoom) {
    return boundsFromRegion(props.zoom);
  }

  const pts = simplePoints.value;
  let minX = 0;
  let maxX = Math.max(1, props.xDieCount) * Math.max(1, props.dieSizeX);
  let minY = 0;
  let maxY = Math.max(1, props.yDieCount) * Math.max(1, props.dieSizeY);
  for (const point of pts) {
    minX = Math.min(minX, point.x);
    maxX = Math.max(maxX, point.x);
    minY = Math.min(minY, point.y);
    maxY = Math.max(maxY, point.y);
  }
  return normalizeBounds({ minX, maxX, minY, maxY });
}

function recalcTransform() {
  const size = measureMapElement(containerRef.value);
  if (!size) return;
  mapSize = size;
  transform = buildMapTransform(mapSize, currentBounds(), props.zoom ? 0.95 : 0.9);
}
function getPos(e: MouseEvent): [number, number] {
  return eventToLocalPoint(containerRef.value, e);
}

// Drag
const dragging = ref(false);
const dStart = ref({ x: 0, y: 0 });
const dEnd = ref({ x: 0, y: 0 });
const dragRect = ref<{ x: number; y: number; w: number; h: number } | null>(null);

function onPointerDown(e: PointerEvent) {
  if (e.button !== 0) return;
  recalcTransform();
  drawOverlay();
  const [sx, sy] = getPos(e);
  dStart.value = dEnd.value = { x: sx, y: sy };
  dragging.value = true;
}
function onPointerMove(e: PointerEvent) {
  if (!dragging.value) return;
  const [sx, sy] = getPos(e);
  let ax = sx;
  let ay = sy;
  if (mode.value === "zoomin") {
    ({ x: ax, y: ay } = constrainDragToAspect(dStart.value, { x: sx, y: sy }, mapSize));
  }
  dEnd.value = { x: ax, y: ay };
  dragRect.value = {
    x: Math.min(dStart.value.x, ax),
    y: Math.min(dStart.value.y, ay),
    w: Math.abs(ax - dStart.value.x),
    h: Math.abs(ay - dStart.value.y),
  };
  drawOverlay();
}
async function onPointerUp() {
  if (!dragging.value) return;
  dragging.value = false;
  if (Math.abs(dEnd.value.x - dStart.value.x) < 4 || Math.abs(dEnd.value.y - dStart.value.y) < 4) {
    dragRect.value = null;
    drawOverlay();
    return;
  }
  recalcTransform();
  const [x1, y1] = screenToData(transform, dStart.value.x, dStart.value.y);
  const [x2, y2] = screenToData(transform, dEnd.value.x, dEnd.value.y);
  const x = Math.min(x1, x2),
    X = Math.max(x1, x2),
    y = Math.min(y1, y2),
    Y = Math.max(y1, y2);
  if (mode.value === "zoomin") {
    emit("zoom-in", { x, y, w: X - x, h: Y - y });
  } else {
    const thisSeq = ++selectionSeq;
    const region = { x, y, w: X - x, h: Y - y };
    const immediateIds = getPackedPointIdsInRegion(props.points ?? [], region);
    selectionState.value = new Set([...selectionState.value, ...immediateIds]);
    emit("selection-change", [...selectionState.value]);
    if (props.queryBoxSelection) {
      isBoxSelecting.value = true;
      try {
        const ids = await props.queryBoxSelection(region);
        if (thisSeq !== selectionSeq) return;
        const next = new Set([...selectionState.value, ...ids]);
        if (next.size !== selectionState.value.size) {
          selectionState.value = next;
          emit("selection-change", [...selectionState.value]);
        }
      } finally {
        isBoxSelecting.value = false;
      }
    }
  }
  dragRect.value = null;
  drawOverlay();
}
function drawOverlay() {
  const c = overlayRef.value;
  if (!c || mapSize.width <= 0 || mapSize.height <= 0) return;
  const ctx = prepareOverlayCanvas(c, mapSize);
  if (!ctx) return;

  // Draw highlight defects as purple 3x3 dots
  if (props.highlightDefects && props.highlightDefects.length > 0) {
    ctx.fillStyle = HIGHLIGHT_POINT_COLOR;
    for (const hd of props.highlightDefects) {
      const [sx, sy] = dataToScreen(transform, hd.reticleX, hd.reticleY);
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
    selectionState.value.clear();
    emit("selection-change", []);
  }
}

let _ro: ResizeObserver | null = null;
watch(
  containerRef,
  (el) => {
    _ro?.disconnect();
    if (el) {
      _ro = new ResizeObserver(() => {
        recalcTransform();
        drawOverlay();
      });
      _ro.observe(el);
    }
  },
  { immediate: true },
);

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

watch(
  () => props.zoom,
  () => {
    recalcTransform();
    drawOverlay();
  },
);

watch(
  () => props.selectedIds,
  (incoming) => {
    if (isBoxSelecting.value || !incoming) return;
    const cur = selectionState.value;
    let changed = false;
    for (const id of incoming) {
      if (!cur.has(id)) {
        cur.add(id);
        changed = true;
      }
    }
    for (const id of cur) {
      if (!incoming.has(id)) {
        cur.delete(id);
        changed = true;
      }
    }
    if (changed) selectionState.value = new Set(cur);
  },
  { immediate: true },
);

watch(
  () => props.highlightDefects,
  () => {
    drawOverlay();
  },
);
</script>

<template>
  <div ref="containerRef" class="srm-wrap">
    <div v-if="pointCount === 0" class="srm-empty">No points</div>
    <SimpleReticleMap
      v-else
      :points="simplePoints"
      :colorMap="props.colorMap ?? {}"
      :xDieCount="xDieCount"
      :yDieCount="yDieCount"
      :dieSizeX="dieSizeX"
      :dieSizeY="dieSizeY"
      :zoom="props.zoom ?? undefined"
    />
    <canvas
      v-if="pointCount > 0"
      ref="overlayRef"
      class="srm-ol"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @pointerleave="onPointerUp"
      @dblclick="onDblClick"
    />
    <div v-if="pointCount > 0" class="srm-footer">
      {{ pointCount }} {{ pointCount === 1 ? "point" : "points" }}
    </div>
  </div>
</template>

<style scoped>
.srm-wrap {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.srm-ol {
  position: absolute;
  inset: 0;
  pointer-events: auto;
  touch-action: none;
  z-index: 1;
}
.srm-empty {
  display: grid;
  flex: 1;
  place-items: center;
  color: var(--text-color-3, #888);
  font-size: 12px;
}
.srm-footer {
  padding: 6px;
  color: #888;
  font-size: 12px;
  text-align: center;
}
.srm-footer {
  position: absolute;
  right: 0;
  bottom: 0;
  pointer-events: none;
}
</style>
