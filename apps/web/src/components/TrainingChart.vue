<script setup lang="ts">
import { computed } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { LineChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsOption } from "echarts";

import type { TrainingEvent } from "../types";

use([CanvasRenderer, GridComponent, LegendComponent, LineChart, TooltipComponent]);

type MetricsArtifact = Record<string, unknown> | null;

interface TrainingMetric {
  epoch: number;
  loss: number;
}

const props = defineProps<{
  events: TrainingEvent[];
  metricsArtifact?: MetricsArtifact;
}>();

const metrics = computed<TrainingMetric[]>(() =>
  props.events
    .map((event) => {
      const { epoch, loss } = event.payload;

      if (typeof epoch !== "number" || typeof loss !== "number") {
        return null;
      }

      return { epoch, loss };
    })
    .filter((metric): metric is TrainingMetric => metric !== null)
    .sort((left, right) => left.epoch - right.epoch),
);

const aggregateStats = computed(() => {
  const metricsArtifact = props.metricsArtifact;
  if (!metricsArtifact) {
    return [] as Array<{ label: string; value: string }>;
  }

  const stats: Array<{ label: string; value: string }> = [];
  for (const [key, rawValue] of Object.entries(metricsArtifact)) {
    if (rawValue === null || typeof rawValue === "object") {
      continue;
    }
    stats.push({
      label: key.replace(/_/g, " "),
      value: String(rawValue),
    });
  }
  return stats;
});

const labelBreakdown = computed(() => {
  const labels = props.metricsArtifact?.labels;
  if (!labels || typeof labels !== "object" || Array.isArray(labels)) {
    return [] as Array<{ label: string; count: string }>;
  }

  return Object.entries(labels)
    .map(([label, count]) => ({ label, count: String(count) }))
    .sort((left, right) => left.label.localeCompare(right.label));
});

const hasArtifactSummary = computed(() => aggregateStats.value.length > 0 || labelBreakdown.value.length > 0);

const option = computed<EChartsOption>(() => ({
  backgroundColor: "transparent",
  grid: {
    left: 12,
    right: 24,
    top: 24,
    bottom: 20,
    containLabel: true,
  },
  tooltip: {
    trigger: "axis",
  },
  xAxis: {
    type: "value",
    name: "Epoch",
    minInterval: 1,
    splitLine: {
      lineStyle: {
        opacity: 0.12,
      },
    },
  },
  yAxis: {
    type: "value",
    name: "Loss",
    scale: true,
    splitLine: {
      lineStyle: {
        opacity: 0.12,
      },
    },
  },
  series: [
    {
      type: "line",
      name: "Loss",
      data: metrics.value.map(({ epoch, loss }) => [epoch, loss]),
      showSymbol: true,
      symbolSize: 8,
      lineStyle: {
        width: 3,
      },
      itemStyle: {
        color: "#4f9cff",
      },
      emphasis: {
        focus: "series",
      },
      smooth: true,
    },
  ],
}));
</script>

<template>
  <section class="training-chart">
    <n-empty v-if="metrics.length === 0 && !hasArtifactSummary" description="No training metrics available yet" />
    <VChart
      v-else-if="metrics.length > 0"
      class="training-chart__plot"
      :option="option"
      theme="dark"
      autoresize
    />
    <n-space v-else vertical size="large">
      <n-grid v-if="aggregateStats.length > 0" :cols="3" :x-gap="12" :y-gap="12">
        <n-gi v-for="item in aggregateStats" :key="item.label">
          <n-statistic :label="item.label" :value="item.value" />
        </n-gi>
      </n-grid>

      <n-card v-if="labelBreakdown.length > 0" size="small" embedded title="Label Breakdown">
        <n-grid :cols="2" :x-gap="12" :y-gap="8">
          <n-gi v-for="item in labelBreakdown" :key="item.label">
            <n-space justify="space-between" align="center">
              <n-text>{{ item.label }}</n-text>
              <n-tag size="small" type="info">{{ item.count }}</n-tag>
            </n-space>
          </n-gi>
        </n-grid>
      </n-card>
    </n-space>
  </section>
</template>

<style scoped>
.training-chart {
  width: 100%;
  aspect-ratio: 16 / 9;
  border-radius: 16px;
  background:
    linear-gradient(180deg, rgba(16, 24, 40, 0.92), rgba(9, 14, 24, 0.96)),
    radial-gradient(circle at top left, rgba(79, 156, 255, 0.12), transparent 42%);
  padding: 16px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.24);
}

.training-chart__plot {
  width: 100%;
  height: 100%;
}
</style>
