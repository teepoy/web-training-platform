<!--
  WaferMapWidget — high-density scatter map constrained to a wafer circle.

  Inline data shape:
    {
      inline: {
        points: Array<{ id: string; x: number; y: number; value?: number } | [string, number, number, number?]>
      }
    }

  Config props:
    interaction  SidebarWidgetInteractionConfig  — enables linked selection/filter intents
    maxPoints    number                          — optional hard cap for rendered points
-->
<script setup lang="ts">
import { computed, inject, ref, shallowRef, watch } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import type { EChartsOption } from "echarts";
import type { ECElementEvent } from "echarts/core";
import { LineChart, ScatterChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import KDBush from "kdbush";
import {
  SIDEBAR_WIDGET_INTERACTION_KEY,
  type SidebarWidgetIntent,
  type SidebarWidgetInteractionConfig,
} from "../widgetContract";

use([LineChart, ScatterChart, GridComponent, TooltipComponent, CanvasRenderer]);

interface RawPointObject {
  id: string;
  x: number;
  y: number;
  value?: number;
}

type RawPointTuple = [string, number, number, number?];

const props = defineProps<{
  data?: Record<string, unknown> | null;
  config?: Record<string, unknown>;
  size?: "compact" | "normal" | "large";
}>();

const interaction = inject(SIDEBAR_WIDGET_INTERACTION_KEY, null);

const chartRootRef = ref<HTMLElement | null>(null);

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

const interactionConfig = computed<SidebarWidgetInteractionConfig | null>(() => {
  const raw = props.config?.interaction;
  if (!raw || typeof raw !== "object") {
    return null;
  }
  return raw as SidebarWidgetInteractionConfig;
});

const maxPoints = computed(() => {
  const parsed = Number(props.config?.maxPoints ?? 0);
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : null;
});

const maxEmitIds = computed(() => {
  const parsed = Number(props.config?.maxEmitIds ?? 50000);
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : 50000;
});

const normalizedPoints = computed<Array<{ id: string; x: number; y: number; value: number }>>(() => {
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

  const parsed: Array<{ id: string; x: number; y: number; value: number }> = [];
  const limit = maxPoints.value;

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
      if (x * x + y * y > 1) {
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
    if (x * x + y * y > 1) {
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
    const index = new KDBush(points.length, 64, Float32Array);
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

const selectedIds = computed(() => {
  const cfg = interactionConfig.value;
  if (!cfg?.collection) {
    return new Set<string>();
  }
  const ids = interaction?.value.state.collections?.[cfg.collection]?.selection.ids ?? [];
  return new Set(ids);
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
  const points: Array<[number, number]> = [];
  const steps = 180;
  for (let i = 0; i <= steps; i += 1) {
    const theta = (Math.PI * 2 * i) / steps;
    points.push([Math.cos(theta), Math.sin(theta)]);
  }
  return points;
});

function emitIntent(intent: SidebarWidgetIntent): void {
  interaction?.value.dispatch(intent);
}

function selectionIntentType(entity: SidebarWidgetInteractionConfig["entity"]): SidebarWidgetIntent["type"] {
  if (entity === "prediction") {
    return "select-predictions";
  }
  return "select-samples";
}

function emitSelection(ids: string[], operation: SidebarWidgetIntent["operation"]): void {
  const cfg = interactionConfig.value;
  if (!cfg?.emitSelection || !cfg.collection) {
    return;
  }

  emitIntent({
    type: selectionIntentType(cfg.entity),
    operation,
    values: ids,
    sourcePanelId: "wafer-map",
    metadata: {
      collection: cfg.collection,
      entity: cfg.entity,
      target: "selection",
    },
  });
}

function emitFilter(ids: string[], operation: SidebarWidgetIntent["operation"]): void {
  const cfg = interactionConfig.value;
  if (!cfg?.filterFromSelection || !cfg.collection) {
    return;
  }

  emitIntent({
    type: "apply-filter",
    operation,
    values: ids,
    sourcePanelId: "wafer-map",
    metadata: {
      collection: cfg.collection,
      entity: cfg.entity,
      target: "filter",
      filterMode: ids.length > 0 ? "selected-only" : "all",
    },
  });
}

function onPointClick(params: ECElementEvent): void {
  const data = Array.isArray(params.data) ? params.data : null;
  const pointId = data && typeof data[2] === "string" ? data[2] : null;
  if (!pointId) {
    return;
  }

  const mouseEvent = params.event?.event as MouseEvent | undefined;
  const operation: SidebarWidgetIntent["operation"] =
    mouseEvent?.metaKey || mouseEvent?.ctrlKey ? "toggle" : "replace";

  emitSelection([pointId], operation);
  if (operation === "replace") {
    emitFilter([pointId], "replace");
  }
}

function clearSelectionAndFilter(): void {
  const cfg = interactionConfig.value;
  if (!cfg?.collection) {
    return;
  }
  emitIntent({
    type: "clear-selection",
    operation: "clear",
    values: [],
    sourcePanelId: "wafer-map",
    metadata: {
      collection: cfg.collection,
      entity: cfg.entity,
      target: "both",
    },
  });
}

function toDataX(localX: number, width: number): number {
  if (width <= 0) {
    return 0;
  }
  return (localX / width) * 2 - 1;
}

function toDataY(localY: number, height: number): number {
  if (height <= 0) {
    return 0;
  }
  return 1 - (localY / height) * 2;
}

function rangeSelectionFromDrag(): string[] {
  const root = chartRootRef.value;
  const index = pointIndex.value;
  if (!root || !index) {
    return [];
  }

  const width = root.clientWidth;
  const height = root.clientHeight;
  const x0 = Math.min(dragState.value.startX, dragState.value.endX);
  const y0 = Math.min(dragState.value.startY, dragState.value.endY);
  const x1 = Math.max(dragState.value.startX, dragState.value.endX);
  const y1 = Math.max(dragState.value.startY, dragState.value.endY);

  const minX = toDataX(x0, width);
  const maxX = toDataX(x1, width);
  const maxY = toDataY(y0, height);
  const minY = toDataY(y1, height);

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
  if (ids.length === 0) {
    emitSelection([], "replace");
    emitFilter([], "replace");
  } else {
    emitSelection(ids, "replace");
    emitFilter(ids, "replace");
  }

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

function onDragMove(event: PointerEvent): void {
  if (!dragState.value.active) {
    return;
  }
  const root = chartRootRef.value;
  if (!root) {
    return;
  }
  const rect = root.getBoundingClientRect();
  dragState.value.endX = event.clientX - rect.left;
  dragState.value.endY = event.clientY - rect.top;
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

const chartOption = computed<EChartsOption>(() => {
  const series: Extract<EChartsOption["series"], unknown[]> = [
    {
      name: "wafer-boundary",
      type: "line",
      data: waferBoundaryPoints.value,
      lineStyle: {
        width: 1,
        color: "rgba(120, 180, 220, 0.55)",
      },
      areaStyle: {
        color: "rgba(120, 180, 220, 0.06)",
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
      symbolSize: 2,
      data: normalizedPoints.value.map((point) => [point.x, point.y, point.id, point.value]),
      itemStyle: {
        color: "rgba(147, 204, 255, 0.55)",
      },
      emphasis: {
        itemStyle: {
          color: "#f7c948",
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
      symbolSize: 4,
      itemStyle: {
        color: "#f7c948",
      },
      silent: true,
      z: 3,
    });
  }

  return {
    backgroundColor: "transparent",
    animation: false,
    grid: {
      left: 12,
      right: 12,
      top: 12,
      bottom: 12,
      containLabel: false,
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
        const x = typeof row[0] === "number" ? row[0].toFixed(4) : "n/a";
        const y = typeof row[1] === "number" ? row[1].toFixed(4) : "n/a";
        return `id: <b>${id}</b><br/>x: ${x}<br/>y: ${y}`;
      },
    },
    xAxis: {
      type: "value",
      min: -1,
      max: 1,
      show: false,
    },
    yAxis: {
      type: "value",
      min: -1,
      max: 1,
      show: false,
    },
    series,
  };
});

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
      </div>
      <div class="wmw-perf">
        <span>index {{ perf.indexMs.toFixed(2) }}ms</span>
        <span>query {{ perf.queryMs.toFixed(2) }}ms</span>
        <span v-if="perf.selectedTotal > 0">{{ perf.emittedTotal }}/{{ perf.selectedTotal }} emitted</span>
        <span v-if="perf.truncated" class="wmw-perf--warn">truncated</span>
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
  color: rgba(255, 255, 255, 0.4);
  padding: 12px 0;
  text-align: center;
}

.wmw-chart {
  width: 100%;
}

.wmw-chart-wrap {
  position: relative;
  width: 100%;
  touch-action: none;
}

.wmw-selection-rect {
  position: absolute;
  border: 1px solid rgba(247, 201, 72, 0.85);
  background: rgba(247, 201, 72, 0.18);
  pointer-events: none;
}

.wmw-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-top: 6px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.55);
}

.wmw-clear {
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 4px;
  color: rgba(255, 255, 255, 0.85);
  font-size: 10px;
  padding: 2px 8px;
  cursor: pointer;
}

.wmw-clear:hover {
  background: rgba(255, 255, 255, 0.15);
}

.wmw-perf {
  display: flex;
  justify-content: center;
  gap: 8px;
  margin-top: 4px;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.4);
}

.wmw-perf--warn {
  color: rgba(255, 200, 120, 0.95);
}
</style>
