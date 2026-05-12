<!--
  WaferMapWidget — high-density scatter map constrained to a wafer circle.

  Coordinate domain: nanometers, fixed to ±WAFER_RADIUS_NM on both axes.
  The plotting area is rendered as a square regardless of container aspect
  so brush math and the wafer edge stay 1:1 even after sidebar resize.

  Inline data shape:
    {
      inline: {
        points: Array<{ id: string; x: number; y: number; value?: number } | [string, number, number, number?]>
      }
    }

  Config props:
    interaction    SidebarWidgetInteractionConfig  — enables linked selection/filter intents
    maxPoints      number                          — optional hard cap for rendered points
    waferRadiusNm  number                          — overrides default 150_000_000 nm radius
-->
<script setup lang="ts">
import { computed, inject, onMounted, onUnmounted, ref, shallowRef, watch } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { getInstanceByDom, type EChartsOption, type EChartsType } from "echarts";
import type { ECElementEvent } from "echarts/core";
import { LineChart, ScatterChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import KDBush from "kdbush";
import { DATA_PIPELINE_KEY } from "../../composables/useDataPipeline";

use([LineChart, ScatterChart, GridComponent, TooltipComponent, CanvasRenderer]);

const DEFAULT_WAFER_RADIUS_NM = 150_000_000;
const MIN_VIEWPORT_FRACTION = 0.001;
const GRID_BREATHING_PX = 8;

interface RawPointObject {
  id: string;
  x: number;
  y: number;
  value?: number;
}

type RawPointTuple = [string, number, number, number?];

type IdsOperation = "clear" | "replace" | "add" | "remove" | "toggle";

interface WaferInteractionConfig {
  collection?: string;
  entity?: string;
  emitSelection?: boolean;
  filterFromSelection?: boolean;
}

interface WaferPoint {
  id: string;
  x: number;
  y: number;
  value: number;
}

interface WaferBenchmarkConfig {
  enabled?: boolean;
  pointCount?: number;
  queryIterations?: number;
  queryBoxSize?: number;
}

interface WaferDieGridConfig {
  dieWidthNm: number;
  dieHeightNm: number;
  originX: number;
  originY: number;
}

const props = defineProps<{
  data?: Record<string, unknown> | null;
  config?: Record<string, unknown>;
  size?: "compact" | "normal" | "large";
}>();

const pipeline = inject(DATA_PIPELINE_KEY)!;
const waferNode = pipeline.register("wafer-map");

const chartRootRef = ref<HTMLElement | null>(null);
const chartInstance = shallowRef<EChartsType | null>(null);

const containerSize = ref({ w: 1, h: 1 });

const dragState = ref({
  active: false,
  startX: 0,
  startY: 0,
  endX: 0,
  endY: 0,
});

const perf = ref({
  indexMs: 0,
  queryMs: 0,
  selectedTotal: 0,
  emittedTotal: 0,
  truncated: false,
});

const benchmark = ref({
  enabled: false,
  pointCount: 0,
  generationMs: 0,
  iterations: 0,
  queryAvgMs: 0,
  queryP95Ms: 0,
  queryMaxMs: 0,
  avgSelected: 0,
});

const waferRadius = computed(() => {
  const parsed = Number(props.config?.waferRadiusNm ?? DEFAULT_WAFER_RADIUS_NM);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_WAFER_RADIUS_NM;
});

const interactionConfig = computed<WaferInteractionConfig | null>(() => {
  const raw = props.config?.interaction;
  if (!raw || typeof raw !== "object") {
    return null;
  }
  return raw as WaferInteractionConfig;
});

const maxPoints = computed(() => {
  const parsed = Number(props.config?.maxPoints ?? 0);
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : null;
});

const maxEmitIds = computed(() => {
  const parsed = Number(props.config?.maxEmitIds ?? 50000);
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : 50000;
});

const benchmarkConfig = computed<WaferBenchmarkConfig>(() => {
  const raw = props.config?.benchmark;
  if (!raw || typeof raw !== "object") {
    return { enabled: false };
  }
  return raw as WaferBenchmarkConfig;
});

const scatterSize = computed(() => {
  const parsed = Number(props.config?.scatterSize ?? 1);
  if (!Number.isFinite(parsed)) return 1;
  return Math.max(0.1, Math.min(20, parsed));
});

const dieGridConfig = computed<WaferDieGridConfig>(() => {
  const raw = props.config?.dieGrid;
  if (!raw || typeof raw !== "object") {
    return { dieWidthNm: 6_000_000, dieHeightNm: 3_000_000, originX: 0, originY: 0 };
  }
  const obj = raw as Record<string, unknown>;
  const dw = Number(obj.dieWidthNm ?? 6_000_000);
  const dh = Number(obj.dieHeightNm ?? 3_000_000);
  const ox = Number(obj.originX ?? 0);
  const oy = Number(obj.originY ?? 0);
  return {
    dieWidthNm: Number.isFinite(dw) ? dw : 6_000_000,
    dieHeightNm: Number.isFinite(dh) ? dh : 3_000_000,
    originX: Number.isFinite(ox) ? ox : 0,
    originY: Number.isFinite(oy) ? oy : 0,
  };
});

const generatedPoints = ref<WaferPoint[] | null>(null);

function generateBenchmarkPoints(count: number, radius: number): WaferPoint[] {
  const safeCount = Number.isFinite(count) && count > 0 ? Math.floor(count) : 1_000_000;
  const points: WaferPoint[] = new Array(safeCount);
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));

  for (let i = 0; i < safeCount; i += 1) {
    const ratio = (i + 0.5) / safeCount;
    const r = Math.sqrt(ratio) * radius;
    const theta = i * goldenAngle;
    points[i] = {
      id: `bench-${i}`,
      x: r * Math.cos(theta),
      y: r * Math.sin(theta),
      value: 1,
    };
  }

  return points;
}

watch(
  [benchmarkConfig, waferRadius],
  ([cfg, radius]) => {
    const enabled = Boolean(cfg.enabled);
    if (!enabled) {
      generatedPoints.value = null;
      benchmark.value = {
        ...benchmark.value,
        enabled: false,
        pointCount: 0,
        generationMs: 0,
      };
      return;
    }

    const pointCount = Number(cfg.pointCount ?? 1_000_000);
    const start = performance.now();
    generatedPoints.value = generateBenchmarkPoints(pointCount, radius);
    benchmark.value = {
      ...benchmark.value,
      enabled: true,
      pointCount: generatedPoints.value.length,
      generationMs: Number((performance.now() - start).toFixed(2)),
    };
  },
  { immediate: true, deep: true },
);

const normalizedPoints = computed<WaferPoint[]>(() => {
  if (benchmarkConfig.value.enabled && generatedPoints.value) {
    return generatedPoints.value;
  }

  if (!props.data) {
    return [];
  }

  const raw = (props.data as Record<string, unknown>).inline ?? props.data;
  if (!raw || typeof raw !== "object") {
    return [];
  }

  const points = (raw as Record<string, unknown>).points;
  if (!Array.isArray(points)) {
    return [];
  }

  const parsed: WaferPoint[] = [];
  const limit = maxPoints.value;
  const radiusSquared = waferRadius.value * waferRadius.value;

  for (let i = 0; i < points.length; i += 1) {
    if (limit != null && parsed.length >= limit) {
      break;
    }

    const point = points[i];
    if (Array.isArray(point)) {
      const tuple = point as RawPointTuple;
      const id = typeof tuple[0] === "string" ? tuple[0] : "";
      const x = Number(tuple[1]);
      const y = Number(tuple[2]);
      const value = Number(tuple[3] ?? 1);
      if (!id || !Number.isFinite(x) || !Number.isFinite(y)) {
        continue;
      }
      if (x * x + y * y > radiusSquared) {
        continue;
      }
      parsed.push({ id, x, y, value: Number.isFinite(value) ? value : 1 });
      continue;
    }

    if (!point || typeof point !== "object") {
      continue;
    }

    const obj = point as RawPointObject;
    const id = typeof obj.id === "string" ? obj.id : "";
    const x = Number(obj.x);
    const y = Number(obj.y);
    const value = Number(obj.value ?? 1);
    if (!id || !Number.isFinite(x) || !Number.isFinite(y)) {
      continue;
    }
    if (x * x + y * y > radiusSquared) {
      continue;
    }
    parsed.push({ id, x, y, value: Number.isFinite(value) ? value : 1 });
  }

  return parsed;
});

const pointIds = computed(() => normalizedPoints.value.map((point) => point.id));

const pointIndex = shallowRef<KDBush | null>(null);

watch(
  normalizedPoints,
  (points) => {
    const start = performance.now();
    const index = new KDBush(points.length, 64, Float64Array);
    for (let i = 0; i < points.length; i += 1) {
      index.add(points[i].x, points[i].y);
    }
    index.finish();
    pointIndex.value = index;
    perf.value = {
      ...perf.value,
      indexMs: Number((performance.now() - start).toFixed(2)),
      queryMs: 0,
      selectedTotal: 0,
      emittedTotal: 0,
      truncated: false,
    };
  },
  { immediate: true },
);

function runIndexQueryBenchmark(): void {
  const index = pointIndex.value;
  const cfg = benchmarkConfig.value;
  if (!index || !benchmark.value.enabled) {
    return;
  }

  const iterationsRaw = Number(cfg.queryIterations ?? 16);
  const iterations = Number.isFinite(iterationsRaw) && iterationsRaw > 0
    ? Math.floor(iterationsRaw)
    : 16;
  const radius = waferRadius.value;
  const boxSizeRaw = Number(cfg.queryBoxSize ?? 0.22);
  const fraction = Math.min(0.95, Math.max(0.01, Number.isFinite(boxSizeRaw) ? boxSizeRaw : 0.22));
  const half = (fraction * radius);

  const times: number[] = [];
  let selectedTotal = 0;

  for (let i = 0; i < iterations; i += 1) {
    const cx = -radius + (2 * radius * (i + 0.5)) / iterations;
    const cy = -radius + (2 * radius * (((i * 7) % iterations) + 0.5)) / iterations;
    const minX = Math.max(-radius, cx - half);
    const maxX = Math.min(radius, cx + half);
    const minY = Math.max(-radius, cy - half);
    const maxY = Math.min(radius, cy + half);

    const start = performance.now();
    const matches = index.range(minX, minY, maxX, maxY);
    const elapsed = performance.now() - start;
    times.push(elapsed);
    selectedTotal += matches.length;
  }

  times.sort((a, b) => a - b);
  const avg = times.reduce((sum, time) => sum + time, 0) / times.length;
  const p95 = times[Math.max(0, Math.floor(times.length * 0.95) - 1)] ?? 0;
  const max = times[times.length - 1] ?? 0;

  benchmark.value = {
    ...benchmark.value,
    iterations,
    queryAvgMs: Number(avg.toFixed(2)),
    queryP95Ms: Number(p95.toFixed(2)),
    queryMaxMs: Number(max.toFixed(2)),
    avgSelected: Math.round(selectedTotal / iterations),
  };
}

watch([pointIndex, benchmarkConfig], () => {
  if (benchmarkConfig.value.enabled && pointIndex.value) {
    runIndexQueryBenchmark();
  }
}, { immediate: true, deep: true });

const selectedIds = computed(() => {
  return waferNode.annotation.value?.ids ?? new Set<string>();
});

const selectedCount = computed(() => selectedIds.value.size);

const shouldRenderSelectedOverlay = computed(
  () => normalizedPoints.value.length <= 150000,
);

const selectedPoints = computed(() => {
  if (!shouldRenderSelectedOverlay.value || selectedIds.value.size === 0) {
    return [] as Array<[number, number, string]>;
  }
  return normalizedPoints.value
    .filter((point) => selectedIds.value.has(point.id))
    .map((point) => [point.x, point.y, point.id]);
});

const waferBoundaryPoints = computed(() => {
  const radius = waferRadius.value;
  const points: Array<[number, number]> = [];
  const steps = 180;
  for (let i = 0; i <= steps; i += 1) {
    const theta = (Math.PI * 2 * i) / steps;
    points.push([radius * Math.cos(theta), radius * Math.sin(theta)]);
  }
  return points;
});

function applyIdsOperation(
  currentIds: string[],
  values: string[],
  operation: IdsOperation,
): string[] {
  const current = new Set(currentIds);
  const incoming = values.filter((value) => value.trim().length > 0);

  if (operation === "clear") {
    return [];
  }

  if (operation === "replace") {
    return [...new Set(incoming)];
  }

  if (operation === "add") {
    incoming.forEach((value) => current.add(value));
    return Array.from(current);
  }

  if (operation === "remove") {
    incoming.forEach((value) => current.delete(value));
    return Array.from(current);
  }

  if (operation === "toggle") {
    incoming.forEach((value) => {
      if (current.has(value)) {
        current.delete(value);
      } else {
        current.add(value);
      }
    });
    return Array.from(current);
  }

  return currentIds;
}

function onPointClick(params: ECElementEvent): void {
  const data = Array.isArray(params.data) ? params.data : null;
  const pointId = data && typeof data[2] === "string" ? data[2] : null;
  if (!pointId) {
    return;
  }

  const mouseEvent = params.event?.event as MouseEvent | undefined;
  const operation: IdsOperation =
    mouseEvent?.metaKey || mouseEvent?.ctrlKey ? "toggle" : "replace";

  const currentIds = Array.from(selectedIds.value);
  const nextIds = applyIdsOperation(currentIds, [pointId], operation);
  waferNode.annotate("selected", nextIds);
}

function clearSelectionAndFilter(): void {
  waferNode.clear();
}

const viewport = ref({
  minX: -DEFAULT_WAFER_RADIUS_NM,
  maxX: DEFAULT_WAFER_RADIUS_NM,
  minY: -DEFAULT_WAFER_RADIUS_NM,
  maxY: DEFAULT_WAFER_RADIUS_NM,
});

watch(
  waferRadius,
  (radius) => {
    viewport.value = { minX: -radius, maxX: radius, minY: -radius, maxY: radius };
  },
  { immediate: true },
);

const gridInsets = computed(() => {
  const w = Math.max(1, containerSize.value.w);
  const h = Math.max(1, containerSize.value.h);
  const side = Math.max(1, Math.min(w, h) - GRID_BREATHING_PX * 2);
  const left = (w - side) / 2;
  const top = (h - side) / 2;
  return {
    left: Math.max(0, left),
    right: Math.max(0, w - left - side),
    top: Math.max(0, top),
    bottom: Math.max(0, h - top - side),
  };
});

function getDataCoords(localX: number, localY: number): [number, number] {
  const insets = gridInsets.value;
  const w = Math.max(1, containerSize.value.w);
  const h = Math.max(1, containerSize.value.h);

  const gridWidth = Math.max(1, w - insets.left - insets.right);
  const gridHeight = Math.max(1, h - insets.top - insets.bottom);

  const gridX = localX - insets.left;
  const gridY = localY - insets.top;

  const fracX = Math.max(0, Math.min(1, gridX / gridWidth));
  const fracY = Math.max(0, Math.min(1, 1 - gridY / gridHeight));

  const { minX, maxX, minY, maxY } = viewport.value;
  return [
    minX + fracX * (maxX - minX),
    minY + fracY * (maxY - minY),
  ];
}

function rangeSelectionFromDrag(): string[] {
  const root = chartRootRef.value;
  const index = pointIndex.value;
  if (!root || !index) {
    return [];
  }

  const x0 = dragState.value.startX;
  const y0 = dragState.value.startY;
  const x1 = dragState.value.endX;
  const y1 = dragState.value.endY;

  const [dataX0, dataY0] = getDataCoords(x0, y0);
  const [dataX1, dataY1] = getDataCoords(x1, y1);

  const minX = Math.min(dataX0, dataX1);
  const maxX = Math.max(dataX0, dataX1);
  const minY = Math.min(dataY0, dataY1);
  const maxY = Math.max(dataY0, dataY1);

  const queryStart = performance.now();
  const pointIndexes = index.range(minX, minY, maxX, maxY);
  const ids: string[] = [];
  const knownIds = pointIds.value;
  const limit = maxEmitIds.value;

  for (let i = 0; i < pointIndexes.length; i += 1) {
    if (ids.length >= limit) {
      break;
    }
    const id = knownIds[pointIndexes[i]];
    if (id) {
      ids.push(id);
    }
  }

  perf.value = {
    ...perf.value,
    queryMs: Number((performance.now() - queryStart).toFixed(2)),
    selectedTotal: pointIndexes.length,
    emittedTotal: ids.length,
    truncated: pointIndexes.length > ids.length,
  };

  return ids;
}

function finishDragSelection(): void {
  const dx = Math.abs(dragState.value.endX - dragState.value.startX);
  const dy = Math.abs(dragState.value.endY - dragState.value.startY);
  if (dx < 4 || dy < 4) {
    dragState.value.active = false;
    return;
  }

  const ids = rangeSelectionFromDrag();
  waferNode.annotate("selected", ids);

  dragState.value.active = false;
}

function onDragStart(event: PointerEvent): void {
  if (event.button !== 0) {
    return;
  }
  const root = chartRootRef.value;
  if (!root) {
    return;
  }

  const rect = root.getBoundingClientRect();
  dragState.value = {
    active: true,
    startX: event.clientX - rect.left,
    startY: event.clientY - rect.top,
    endX: event.clientX - rect.left,
    endY: event.clientY - rect.top,
  };
}

let dragMoveRaf = 0;
let pendingDragX = 0;
let pendingDragY = 0;

function flushDragMove(): void {
  dragMoveRaf = 0;
  if (!dragState.value.active) {
    return;
  }
  dragState.value.endX = pendingDragX;
  dragState.value.endY = pendingDragY;
}

function onDragMove(event: PointerEvent): void {
  if (!dragState.value.active) {
    return;
  }
  const root = chartRootRef.value;
  if (!root) {
    return;
  }
  const rect = root.getBoundingClientRect();
  pendingDragX = event.clientX - rect.left;
  pendingDragY = event.clientY - rect.top;
  if (dragMoveRaf === 0) {
    dragMoveRaf = requestAnimationFrame(flushDragMove);
  }
}

function onDragEnd(): void {
  if (!dragState.value.active) {
    return;
  }
  finishDragSelection();
}

const chartHeight = computed(() => {
  switch (props.size) {
    case "compact":
      return "180px";
    case "large":
      return "340px";
    default:
      return "260px";
  }
});

const isZoomed = computed(() => {
  const radius = waferRadius.value;
  const { minX, maxX, minY, maxY } = viewport.value;
  return minX > -radius || maxX < radius || minY > -radius || maxY < radius;
});

function resetZoom() {
  const radius = waferRadius.value;
  viewport.value = { minX: -radius, maxX: radius, minY: -radius, maxY: radius };
  chartInstance.value?.setOption(viewportAxis.value, false);
}

let wheelRaf = 0;
let wheelDeltaY = 0;
let wheelLocalX = 0;
let wheelLocalY = 0;

function applyWheelZoom(): void {
  wheelRaf = 0;
  const root = chartRootRef.value;
  if (!root) return;

  const radius = waferRadius.value;
  const localX = wheelLocalX;
  const localY = wheelLocalY;

  const zoomFactor = wheelDeltaY > 0 ? 1.15 : 1 / 1.15;
  const [dataX, dataY] = getDataCoords(localX, localY);

  const width = viewport.value.maxX - viewport.value.minX;
  const height = viewport.value.maxY - viewport.value.minY;

  const minSpan = MIN_VIEWPORT_FRACTION * radius;
  const maxSpan = 2 * radius;
  const newWidth = Math.max(minSpan, Math.min(maxSpan, width * zoomFactor));
  const newHeight = Math.max(minSpan, Math.min(maxSpan, height * zoomFactor));

  const fracX = (dataX - viewport.value.minX) / width;
  const fracY = (dataY - viewport.value.minY) / height;

  let nextMinX = dataX - newWidth * fracX;
  let nextMaxX = dataX + newWidth * (1 - fracX);
  let nextMinY = dataY - newHeight * fracY;
  let nextMaxY = dataY + newHeight * (1 - fracY);

  if (nextMinX < -radius) {
    nextMaxX = Math.min(radius, nextMaxX + (-radius - nextMinX));
    nextMinX = -radius;
  }
  if (nextMaxX > radius) {
    nextMinX = Math.max(-radius, nextMinX - (nextMaxX - radius));
    nextMaxX = radius;
  }
  if (nextMinY < -radius) {
    nextMaxY = Math.min(radius, nextMaxY + (-radius - nextMinY));
    nextMinY = -radius;
  }
  if (nextMaxY > radius) {
    nextMinY = Math.max(-radius, nextMinY - (nextMaxY - radius));
    nextMaxY = radius;
  }

  viewport.value = {
    minX: nextMinX,
    maxX: nextMaxX,
    minY: nextMinY,
    maxY: nextMaxY,
  };

  chartInstance.value?.setOption(viewportAxis.value, false);
}

function onWheel(event: WheelEvent) {
  event.preventDefault();
  const root = chartRootRef.value;
  if (!root) {
    return;
  }
  const rect = root.getBoundingClientRect();
  wheelDeltaY = event.deltaY;
  wheelLocalX = event.clientX - rect.left;
  wheelLocalY = event.clientY - rect.top;
  if (wheelRaf === 0) {
    wheelRaf = requestAnimationFrame(applyWheelZoom);
  }
}

const waferScatterData = computed<Array<[number, number, string, number]>>(() =>
  normalizedPoints.value.map((point) => [point.x, point.y, point.id, point.value]),
);

type LineSegment = [[number, number], [number, number]];

function computeDieGridLines(
  radius: number,
  dieWidth: number,
  dieHeight: number,
  originX: number,
  originY: number,
): LineSegment[] {
  if (radius <= 0 || dieWidth <= 0 || dieHeight <= 0) {
    return [];
  }
  const segments: LineSegment[] = [];

  // Vertical grid lines: x = originX + n * dieWidth
  const vStart = Math.ceil((-radius - originX) / dieWidth);
  const vEnd = Math.floor((radius - originX) / dieWidth);
  for (let n = vStart; n <= vEnd; n += 1) {
    const x = originX + n * dieWidth;
    const absX = Math.abs(x);
    if (absX >= radius) {
      continue;
    }
    const yI = Math.sqrt(radius * radius - x * x);
    segments.push([
      [x, -yI],
      [x, yI],
    ]);
  }

  // Horizontal grid lines: y = originY + m * dieHeight
  const hStart = Math.ceil((-radius - originY) / dieHeight);
  const hEnd = Math.floor((radius - originY) / dieHeight);
  for (let m = hStart; m <= hEnd; m += 1) {
    const y = originY + m * dieHeight;
    const absY = Math.abs(y);
    if (absY >= radius) {
      continue;
    }
    const xI = Math.sqrt(radius * radius - y * y);
    segments.push([
      [-xI, y],
      [xI, y],
    ]);
  }

  return segments;
}

const dieGridSeriesData = computed(() => {
  const segments = computeDieGridLines(
    waferRadius.value,
    dieGridConfig.value.dieWidthNm,
    dieGridConfig.value.dieHeightNm,
    dieGridConfig.value.originX,
    dieGridConfig.value.originY,
  );
  if (segments.length === 0) return [];
  // Flatten segments with null separators for disconnected line rendering
  const flat: (number[] | null)[] = [];
  for (const seg of segments) {
    flat.push(seg[0], seg[1], null);
  }
  return flat;
});

const stableChartOption = computed<EChartsOption>(() => {
  const series: Extract<EChartsOption["series"], unknown[]> = [
    {
      name: "wafer-boundary",
      type: "line",
      data: waferBoundaryPoints.value,
      lineStyle: {
        width: 1.5,
        color: "#000000",
      },
      symbol: "none",
      silent: true,
      z: 1,
    },
    {
      name: "wafer",
      type: "scatter",
      large: true,
      largeThreshold: 2000,
      progressive: 20000,
      progressiveThreshold: 30000,
      symbolSize: scatterSize.value,
      data: waferScatterData.value,
      itemStyle: {
        color: "#d83a3a",
      },
      emphasis: {
        itemStyle: {
          color: "#7a1f1f",
        },
      },
      z: 2,
    },
  ];

  if (shouldRenderSelectedOverlay.value) {
    series.push({
      name: "selected",
      type: "scatter",
      data: selectedPoints.value,
      symbolSize: Math.max(4, scatterSize.value + 2),
      itemStyle: {
        color: "#f7c948",
        borderColor: "#7a5c00",
        borderWidth: 1,
      },
      silent: true,
      z: 3,
    });
  }

  if (dieGridSeriesData.value.length > 0) {
    series.push({
      name: "die-grid",
      type: "line",
      data: dieGridSeriesData.value,
      lineStyle: {
        width: 0.5,
        color: "#d0d0d0",
        type: "solid",
      },
      symbol: "none",
      silent: true,
      z: 0,
    });
  }

  return {
    backgroundColor: "#ffffff",
    animation: false,
    grid: {
      left: gridInsets.value.left,
      right: gridInsets.value.right,
      top: gridInsets.value.top,
      bottom: gridInsets.value.bottom,
      containLabel: false,
    },
    xAxis: {
      type: "value" as const,
      min: -DEFAULT_WAFER_RADIUS_NM,
      max: DEFAULT_WAFER_RADIUS_NM,
      show: false,
    },
    yAxis: {
      type: "value" as const,
      min: -DEFAULT_WAFER_RADIUS_NM,
      max: DEFAULT_WAFER_RADIUS_NM,
      show: false,
    },
    tooltip: {
      trigger: "item",
      formatter(params: unknown) {
        let row: unknown[] | null = null;
        if (params && typeof params === "object" && !Array.isArray(params) && "data" in params) {
          const data = (params as { data?: unknown }).data;
          if (Array.isArray(data)) {
            row = data;
          }
        }
        if (!Array.isArray(row)) {
          return "Point";
        }
        const id = typeof row[2] === "string" ? row[2] : "n/a";
        const x = typeof row[0] === "number" ? row[0].toFixed(0) : "n/a";
        const y = typeof row[1] === "number" ? row[1].toFixed(0) : "n/a";
        return `id: <b>${id}</b><br/>x: ${x} nm<br/>y: ${y} nm`;
      },
    },
    series,
  };
});

const viewportAxis = computed(() => ({
  xAxis: {
    type: "value" as const,
    min: viewport.value.minX,
    max: viewport.value.maxX,
    show: false,
  },
  yAxis: {
    type: "value" as const,
    min: viewport.value.minY,
    max: viewport.value.maxY,
    show: false,
  },
}));

const chartOption = computed<EChartsOption>(() => stableChartOption.value);

const selectionRectStyle = computed(() => {
  if (!dragState.value.active) {
    return null;
  }

  const left = Math.min(dragState.value.startX, dragState.value.endX);
  const top = Math.min(dragState.value.startY, dragState.value.endY);
  const width = Math.abs(dragState.value.startX - dragState.value.endX);
  const height = Math.abs(dragState.value.startY - dragState.value.endY);

  return {
    left: `${left}px`,
    top: `${top}px`,
    width: `${width}px`,
    height: `${height}px`,
  };
});

let resizeObserver: ResizeObserver | null = null;

onMounted(() => {
  const root = chartRootRef.value;
  if (!root) return;

  containerSize.value = { w: root.clientWidth || 1, h: root.clientHeight || 1 };

  if (typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        containerSize.value = {
          w: entry.contentRect.width || 1,
          h: entry.contentRect.height || 1,
        };
      }
    });
    resizeObserver.observe(root);
  }

  const chartDom = root.querySelector(".wmw-chart") as HTMLElement;
  if (chartDom) {
    chartInstance.value = getInstanceByDom(chartDom) ?? null;
  }
});

onUnmounted(() => {
  if (dragMoveRaf !== 0) {
    cancelAnimationFrame(dragMoveRaf);
    dragMoveRaf = 0;
  }
  if (wheelRaf !== 0) {
    cancelAnimationFrame(wheelRaf);
    wheelRaf = 0;
  }
  if (resizeObserver) {
    resizeObserver.disconnect();
    resizeObserver = null;
  }
  chartInstance.value = null;
});
</script>

<template>
  <div class="wmw">
    <div v-if="normalizedPoints.length === 0" class="wmw-empty">No wafer points</div>
    <template v-else>
      <div
        ref="chartRootRef"
        class="wmw-chart-wrap"
        :style="{ height: chartHeight }"
        @pointerdown="onDragStart"
        @pointermove="onDragMove"
        @pointerup="onDragEnd"
        @pointercancel="onDragEnd"
        @pointerleave="onDragEnd"
        @wheel="onWheel"
      >
        <VChart
          class="wmw-chart"
          :option="chartOption"
          :style="{ height: chartHeight }"
          autoresize
          @click="onPointClick"
        />
        <div v-if="selectionRectStyle" class="wmw-selection-rect" :style="selectionRectStyle" />
      </div>
      <div class="wmw-footer">
        <span>{{ normalizedPoints.length }} point{{ normalizedPoints.length === 1 ? "" : "s" }}</span>
        <span v-if="selectedCount > 0">{{ selectedCount }} selected</span>
        <button v-if="selectedCount > 0" class="wmw-clear" @click="clearSelectionAndFilter">Clear</button>
        <button v-if="isZoomed" class="wmw-clear" @click="resetZoom">Reset Zoom</button>
      </div>
      <div class="wmw-perf">
        <span>index {{ perf.indexMs.toFixed(2) }}ms</span>
        <span>query {{ perf.queryMs.toFixed(2) }}ms</span>
        <span v-if="perf.selectedTotal > 0">{{ perf.emittedTotal }}/{{ perf.selectedTotal }} emitted</span>
        <span v-if="perf.truncated" class="wmw-perf--warn">truncated</span>
      </div>
      <div v-if="benchmark.enabled" class="wmw-benchmark">
        <span>{{ benchmark.pointCount }} pts</span>
        <span>gen {{ benchmark.generationMs.toFixed(2) }}ms</span>
        <span>q(avg/p95/max) {{ benchmark.queryAvgMs.toFixed(2) }}/{{ benchmark.queryP95Ms.toFixed(2) }}/{{ benchmark.queryMaxMs.toFixed(2) }}ms</span>
        <span>{{ benchmark.avgSelected }} avg hits</span>
        <button class="wmw-run" @click="runIndexQueryBenchmark">Run benchmark</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.wmw {
  width: 100%;
}

.wmw-empty {
  font-size: 12px;
  color: #888;
  padding: 12px 0;
  text-align: center;
}

.wmw-chart {
  width: 100%;
}

.wmw-chart-wrap {
  position: relative;
  width: 100%;
  background: #ffffff;
  border-radius: 4px;
  touch-action: none;
}

.wmw-selection-rect {
  position: absolute;
  border: 1px solid rgba(122, 92, 0, 0.95);
  background: rgba(247, 201, 72, 0.25);
  pointer-events: none;
}

.wmw-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-top: 6px;
  font-size: 11px;
  color: #555;
}

.wmw-clear {
  background: rgba(0, 0, 0, 0.04);
  border: 1px solid rgba(0, 0, 0, 0.16);
  border-radius: 4px;
  color: #333;
  font-size: 10px;
  padding: 2px 8px;
  cursor: pointer;
}

.wmw-clear:hover {
  background: rgba(0, 0, 0, 0.08);
}

.wmw-perf {
  display: flex;
  justify-content: center;
  gap: 8px;
  margin-top: 4px;
  font-size: 10px;
  color: #777;
}

.wmw-perf--warn {
  color: #b45309;
}

.wmw-benchmark {
  display: flex;
  justify-content: center;
  gap: 8px;
  margin-top: 4px;
  font-size: 10px;
  color: #555;
  flex-wrap: wrap;
}

.wmw-run {
  background: rgba(0, 0, 0, 0.04);
  border: 1px solid rgba(0, 0, 0, 0.16);
  border-radius: 4px;
  color: #333;
  font-size: 10px;
  padding: 2px 8px;
  cursor: pointer;
}

.wmw-run:hover {
  background: rgba(0, 0, 0, 0.08);
}
</style>
