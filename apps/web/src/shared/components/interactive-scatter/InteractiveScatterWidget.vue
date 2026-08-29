<!--
  InteractiveScatterWidget — metadata-driven scatter plot for classify sidebar.

  Inline data shape:
    {
      inline: {
        points: Array<{
          id: string
          x: number
          y: number
          label?: string | null
          title?: string | null
          imageSrc?: string | null
        }>
      }
    }

  Config props:
    interaction  SidebarWidgetInteractionConfig  — enables linked selection/filter intents
    xKey         string                          — metadata key to use for x when building fallback points
    yKey         string                          — metadata key to use for y when building fallback points
    colorKey     string                          — optional metadata key used for series grouping
    maxPoints    number                          — optional render cap
-->
<script setup lang="ts">
import { computed, inject } from "vue";
import { useI18n } from "vue-i18n";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import type { EChartsOption } from "echarts";
import type { ECElementEvent } from "echarts/core";
import { ScatterChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { DATA_PIPELINE_KEY } from "../../composables/useDataPipeline";

const { t } = useI18n();

use([ScatterChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

interface ScatterPoint {
  id: string;
  x: number;
  y: number;
  label: string | null;
  title: string | null;
  imageSrc: string | null;
}

const props = defineProps<{
  data?: Record<string, unknown> | null;
  config?: Record<string, unknown>;
  size?: "compact" | "normal" | "large";
}>();

const pipeline = inject(DATA_PIPELINE_KEY)!;
const scatterNode = pipeline.register("interactive-scatter");

interface ScatterInteractionConfig {
  collection?: string;
  entity?: string;
  emitSelection?: boolean;
  filterFromSelection?: boolean;
}

const interactionConfig = computed<ScatterInteractionConfig | null>(() => {
  const raw = props.config?.interaction;
  if (!raw || typeof raw !== "object") {
    return null;
  }
  return raw as ScatterInteractionConfig;
});

const maxPoints = computed(() => {
  const parsed = Number(props.config?.maxPoints ?? 5000);
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : 5000;
});

const normalizedPoints = computed<ScatterPoint[]>(() => {
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

  const parsed: ScatterPoint[] = [];
  for (let i = 0; i < points.length; i += 1) {
    if (parsed.length >= maxPoints.value) {
      break;
    }
    const point = points[i];
    if (!point || typeof point !== "object") {
      continue;
    }
    const row = point as Record<string, unknown>;
    const id = typeof row.id === "string" ? row.id : "";
    const x = Number(row.x);
    const y = Number(row.y);
    if (!id || !Number.isFinite(x) || !Number.isFinite(y)) {
      continue;
    }
    parsed.push({
      id,
      x,
      y,
      label: typeof row.label === "string" ? row.label : null,
      title: typeof row.title === "string" ? row.title : null,
      imageSrc: typeof row.imageSrc === "string" ? row.imageSrc : null,
    });
  }

  return parsed;
});

type IdsOperation = "clear" | "replace" | "add" | "remove" | "toggle";

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

const selectedIds = computed(() => {
  return scatterNode.annotation.value?.ids ?? new Set<string>();
});

function onChartClick(params: ECElementEvent): void {
  const row = Array.isArray(params.data) ? params.data : null;
  const pointId = row && typeof row[2] === "string" ? row[2] : null;
  if (!pointId) {
    return;
  }

  const mouseEvent = params.event?.event as MouseEvent | undefined;
  const operation: IdsOperation = mouseEvent?.metaKey || mouseEvent?.ctrlKey ? "toggle" : "replace";

  const currentIds = Array.from(selectedIds.value);
  const nextIds = applyIdsOperation(currentIds, [pointId], operation);
  scatterNode.annotate("selected", nextIds);
}

function clearSelectionAndFilter(): void {
  scatterNode.clear();
}

const groupedSeries = computed(() => {
  const groups = new Map<string, Array<[number, number, string, string | null, string | null]>>();

  normalizedPoints.value.forEach((point) => {
    const key = point.label ?? "Unlabeled";
    const bucket = groups.get(key) ?? [];
    bucket.push([point.x, point.y, point.id, point.title, point.imageSrc]);
    groups.set(key, bucket);
  });

  return Array.from(groups.entries()).map(([name, data]) => ({
    name,
    type: "scatter" as const,
    symbolSize: 10,
    emphasis: { focus: "series" as const },
    data,
  }));
});

const selectedOverlay = computed(() =>
  normalizedPoints.value
    .filter((point) => selectedIds.value.has(point.id))
    .map((point) => [point.x, point.y, point.id, point.title, point.imageSrc]),
);

const chartHeight = computed(() => {
  switch (props.size) {
    case "compact":
      return "180px";
    case "large":
      return "320px";
    default:
      return "240px";
  }
});

const chartOption = computed<EChartsOption>(() => ({
  animation: false,
  backgroundColor: "transparent",
  legend: {
    top: 0,
    textStyle: { color: "rgba(255,255,255,0.65)", fontSize: 10 },
  },
  grid: {
    left: 12,
    right: 12,
    top: 28,
    bottom: 12,
    containLabel: true,
  },
  tooltip: {
    trigger: "item",
    formatter(params: unknown) {
      let row: unknown[] | null = null;
      let seriesName = "Point";
      if (params && typeof params === "object" && !Array.isArray(params)) {
        if ("data" in params && Array.isArray((params as { data?: unknown }).data)) {
          row = (params as { data?: unknown[] }).data ?? null;
        }
        if (
          "seriesName" in params &&
          typeof (params as { seriesName?: unknown }).seriesName === "string"
        ) {
          seriesName = (params as { seriesName: string }).seriesName;
        }
      }
      if (!row) {
        return seriesName;
      }
      const title = typeof row[3] === "string" && row[3] ? row[3] : row[2];
      const x = typeof row[0] === "number" ? row[0].toFixed(3) : "n/a";
      const y = typeof row[1] === "number" ? row[1].toFixed(3) : "n/a";
      return `${title}<br/>${seriesName}<br/>x: ${x}<br/>y: ${y}`;
    },
  },
  xAxis: {
    type: "value",
    name: "X",
    nameTextStyle: { color: "rgba(255,255,255,0.55)", fontSize: 10 },
    axisLabel: { color: "rgba(255,255,255,0.45)", fontSize: 10 },
    splitLine: { lineStyle: { color: "rgba(255,255,255,0.08)" } },
  },
  yAxis: {
    type: "value",
    name: "Y",
    nameTextStyle: { color: "rgba(255,255,255,0.55)", fontSize: 10 },
    axisLabel: { color: "rgba(255,255,255,0.45)", fontSize: 10 },
    splitLine: { lineStyle: { color: "rgba(255,255,255,0.08)" } },
  },
  series: [
    ...groupedSeries.value,
    {
      name: t("widgets.selected"),
      type: "scatter",
      data: selectedOverlay.value,
      symbolSize: 14,
      itemStyle: {
        color: "#f7c948",
        borderColor: "#ffffff",
        borderWidth: 1,
      },
      silent: true,
      z: 10,
    },
  ],
}));
</script>

<template>
  <div class="isw">
    <div v-if="normalizedPoints.length === 0" class="isw-empty">
      {{ t("widgets.noScatterCoordinates") }}
    </div>
    <template v-else>
      <VChart
        class="isw-chart"
        :option="chartOption"
        :style="{ height: chartHeight }"
        autoresize
        @click="onChartClick"
      />
      <div class="isw-footer">
        <span>{{ t("widgets.pointCount", { count: normalizedPoints.length }) }}</span>
        <span v-if="selectedIds.size > 0">{{
          t("widgets.samplesSelected", { count: selectedIds.size })
        }}</span>
        <button v-if="selectedIds.size > 0" class="isw-clear" @click="clearSelectionAndFilter">
          {{ t("common.clear") }}
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.isw {
  width: 100%;
}

.isw-empty {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.4);
  padding: 12px 0;
  text-align: center;
}

.isw-chart {
  width: 100%;
}

.isw-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-top: 6px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.55);
  flex-wrap: wrap;
}

.isw-clear {
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 4px;
  color: rgba(255, 255, 255, 0.85);
  font-size: 10px;
  padding: 2px 8px;
  cursor: pointer;
}

.isw-clear:hover {
  background: rgba(255, 255, 255, 0.15);
}
</style>
