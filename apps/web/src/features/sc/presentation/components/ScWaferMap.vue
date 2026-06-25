<!--
  ScWaferMap — Wrapper around SimpleWaferMap with selection / zoom-in mode.
  Data format: flat array with 6 int32 values per point:
    [x, y, defect_id, class_number, rough_bin, has_review, x, y, ...]
-->
<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import SimpleWaferMap from "./SimpleWaferMap.vue";
import type { SimpleMapPoint } from "./SimpleMapPoint";
import type { HighlightDefect } from "./types";
import { getPackedPointIdsInRegion } from "./scMapUtils";
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
const HIGHLIGHT_POINT_COLOR = "#A855F7";

interface WaferGeometry {
  centerX: number;
  centerY: number;
  originX: number;
  originY: number;
  dieSizeX: number;
  dieSizeY: number;
}

const props = defineProps<{
  points?: number[];
  waferRadiusNm?: number;
  geometry?: WaferGeometry | null;
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

type Mode = "select" | "zoomin";
const mode = computed(() => props.mode ?? "select");

const isBoxSelecting = ref(false);
let selectionSeq = 0;

const containerRef = ref<HTMLDivElement | null>(null);
const overlayRef = ref<HTMLCanvasElement | null>(null);

const waferRadiusNm = computed(() => props.waferRadiusNm ?? DEFAULT_WAFER_RADIUS_NM);
const pointCount = computed(() => Math.floor((props.points?.length ?? 0) / STRIDE));

const simplePoints = computed<SimpleMapPoint[]>(() => {
  const pts = props.points;
  if (!pts || pts.length === 0) return [];
  const selected = props.selectedIds ?? new Set<number>();
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
      isSelectedFlag: selected.has(defectId),
    };
  }
  return result;
});

// ── Coordinate transform (shared with map wrappers) ──

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

function recalcTransform() {
  const size = measureMapElement(containerRef.value);
  if (!size) return;
  mapSize = size;
  const cx = props.geometry?.centerX ?? 0;
  const cy = props.geometry?.centerY ?? 0;
  if (props.zoom) {
    transform = buildMapTransform(mapSize, boundsFromRegion(props.zoom), 0.95);
  } else {
    const radius = waferRadiusNm.value;
    transform = buildMapTransform(
      mapSize,
      { minX: cx - radius, maxX: cx + radius, minY: cy - radius, maxY: cy + radius },
      1,
    );
  }
}

function getPos(e: MouseEvent): [number, number] {
  return eventToLocalPoint(containerRef.value, e);
}

// ── Drag ──

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

  let ax = sx;
  let ay = sy;
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

  if (mode.value === "zoomin") {
    emit("zoom-in", { x, y, w: X - x, h: Y - y });
  } else {
    void handleBoxSelect({ x, y, w: X - x, h: Y - y });
  }

  dragRect.value = null;
  drawOverlay();
}

function drawOverlay() {
  const cvs = overlayRef.value;
  if (!cvs || mapSize.width <= 0 || mapSize.height <= 0) return;
  const ctx = prepareOverlayCanvas(cvs, mapSize);
  if (!ctx) return;

  // Draw highlight defects as purple 3x3 dots
  if (props.highlightDefects && props.highlightDefects.length > 0) {
    ctx.fillStyle = HIGHLIGHT_POINT_COLOR;
    for (const hd of props.highlightDefects) {
      const [sx, sy] = dataToScreen(transform, hd.waferX, hd.waferY);
      ctx.fillRect(sx - 1.5, sy - 1.5, 3, 3);
    }
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

function onDblClick() {
  if (mode.value === "zoomin" && props.zoom) {
    emit("zoom-in", null);
  } else if (mode.value === "select") {
    selectionSeq += 1;
    emit("selection-change", []);
  }
}

// ── Box select handler ──
async function handleBoxSelect(region: { x: number; y: number; w: number; h: number }) {
  const thisSeq = ++selectionSeq;
  const immediateIds = getPackedPointIdsInRegion(props.points ?? [], region);
  const currentIds = props.selectedIds ?? new Set<number>();
  const merged = new Set([...currentIds, ...immediateIds]);
  emit("selection-change", [...merged]);

  if (!props.queryBoxSelection) {
    return;
  }
  isBoxSelecting.value = true;
  try {
    const ids = await props.queryBoxSelection(region);
    if (thisSeq !== selectionSeq) return;
    const next = new Set([...currentIds, ...ids]);
    if (next.size !== currentIds.size) {
      emit("selection-change", [...next]);
    }
  } finally {
    isBoxSelecting.value = false;
  }
}

// ── Resize ──

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
  () => props.highlightDefects,
  () => {
    drawOverlay();
  },
);

watch(
  () => props.geometry,
  (geo) => {
    recalcTransform();
    drawOverlay();
  },
  { immediate: true },
);
</script>

<template>
  <div ref="containerRef" class="swm-wrap">
    <div v-if="pointCount === 0" class="swm-empty">No points</div>
    <SimpleWaferMap
      v-else
      :points="simplePoints"
      :colorMap="props.colorMap ?? {}"
      :zoom="props.zoom ?? undefined"
      :center-x="props.geometry?.centerX"
      :center-y="props.geometry?.centerY"
      :origin-x="props.geometry?.originX"
      :origin-y="props.geometry?.originY"
      :die-size-x="props.geometry?.dieSizeX"
      :die-size-y="props.geometry?.dieSizeY"
    />
    <canvas
      v-if="pointCount > 0"
      ref="overlayRef"
      class="swm-ol"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @pointerleave="onPointerUp"
      @dblclick="onDblClick"
    />
    <div v-if="pointCount > 0" class="swm-footer">
      {{ pointCount }} {{ pointCount === 1 ? "point" : "points" }}
    </div>
  </div>
</template>

<style scoped>
.swm-wrap {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.swm-ol {
  position: absolute;
  inset: 0;
  pointer-events: auto;
  touch-action: none;
  z-index: 1;
}
.swm-empty {
  display: grid;
  flex: 1;
  place-items: center;
  color: var(--text-color-3, #888);
  font-size: 12px;
}
.swm-footer {
  padding: 6px;
  color: #888;
  font-size: 12px;
  text-align: center;
}
.swm-footer {
  position: absolute;
  right: 0;
  bottom: 0;
  pointer-events: none;
}
</style>
