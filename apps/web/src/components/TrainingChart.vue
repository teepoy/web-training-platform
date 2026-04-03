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

interface TrainingMetric {
  epoch: number;
  loss: number;
}

const props = defineProps<{
  events: TrainingEvent[];
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
    <n-empty v-if="metrics.length === 0" description="No training data yet" />
    <VChart
      v-else
      class="training-chart__plot"
      :option="option"
      theme="dark"
      autoresize
    />
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
