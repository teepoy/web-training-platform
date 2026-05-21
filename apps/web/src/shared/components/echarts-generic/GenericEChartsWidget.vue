<!--
  GenericEChartsWidget — renders any ECharts chart from an inline option object.

  Inline data shape: the full `data` object IS the EChartsOption (or wrapped
  in `{ inline: <EChartsOption> }`).

  Config props:
    height — chart height in px (default depends on panel size)
-->
<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { PieChart, BarChart, LineChart, ScatterChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  DatasetComponent,
  ToolboxComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'

use([
  PieChart,
  BarChart,
  LineChart,
  ScatterChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  DatasetComponent,
  ToolboxComponent,
  CanvasRenderer,
])

const props = defineProps<{
  data?: Record<string, unknown> | null
  config?: Record<string, unknown>
  size?: 'compact' | 'normal' | 'large'
}>()

const chartHeight = computed(() => {
  if (props.config?.height) return `${props.config.height}px`
  switch (props.size) {
    case 'compact': return '160px'
    case 'large': return '320px'
    default: return '220px'
  }
})

const chartOption = computed<EChartsOption | null>(() => {
  if (!props.data) return null
  // Accept either raw EChartsOption or { inline: <option> }
  const raw = (props.data as Record<string, unknown>).inline ?? props.data
  if (!raw || typeof raw !== 'object') return null

  // Merge dark-theme defaults
  return {
    backgroundColor: 'transparent',
    textStyle: { color: 'rgba(255,255,255,0.7)', fontSize: 11 },
    ...(raw as Record<string, unknown>),
  } as EChartsOption
})
</script>

<template>
  <div class="gew">
    <div v-if="!chartOption" class="gew-empty">No chart data</div>
    <VChart
      v-else
      class="gew-chart"
      :option="chartOption"
      :style="{ height: chartHeight }"
      autoresize
    />
  </div>
</template>

<style scoped>
.gew {
  width: 100%;
}
.gew-chart {
  width: 100%;
}
.gew-empty {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.4);
  padding: 12px 0;
  text-align: center;
}
</style>
