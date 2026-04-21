<!--
  LabelDistributionWidget — horizontal bar chart showing label types and counts.

  Accepted props (via sidebarConfig descriptor):
    orientation   'horizontal' | 'vertical'  — bar direction (default 'horizontal')
    showValues    boolean                     — show count labels on bars (default true)
    maxBars       number                      — max labels to show, rest grouped as "Other" (default 20)

  Data comes from the injected ClassifyDashboardContext (stats.label_counts).
-->
<script setup lang="ts">
import { computed, inject } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'
import type { ECElementEvent } from 'echarts/core'
import type { ClassifyDashboardContext } from '../../../composables/useClassifyDashboard'
import {
  SIDEBAR_WIDGET_INTERACTION_KEY,
  type SidebarWidgetIntent,
} from '../widgetContract'

use([CanvasRenderer, GridComponent, BarChart, TooltipComponent])

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

const props = withDefaults(defineProps<{
  orientation?: 'horizontal' | 'vertical'
  showValues?: boolean
  maxBars?: number
}>(), {
  orientation: 'horizontal',
  showValues: true,
  maxBars: 20,
})

// ---------------------------------------------------------------------------
// Injected context
// ---------------------------------------------------------------------------

const ctx = inject<ClassifyDashboardContext>('classifyDashboard')!
const interaction = inject(SIDEBAR_WIDGET_INTERACTION_KEY, null)

// ---------------------------------------------------------------------------
// Colours
// ---------------------------------------------------------------------------

const BAR_COLORS = [
  '#4CAF50', '#2196F3', '#FF9800', '#E91E63', '#9C27B0',
  '#00BCD4', '#FF5722', '#795548', '#607D8B', '#CDDC39',
  '#8BC34A', '#3F51B5', '#FFC107', '#009688', '#673AB7',
  '#F44336', '#03A9F4', '#FFEB3B', '#76FF03', '#FF4081',
]

// ---------------------------------------------------------------------------
// Derived data
// ---------------------------------------------------------------------------

const labelItems = computed<Array<{ label: string; count: number }>>(() => {
  const raw = ctx.stats?.label_counts ?? {}
  const sorted = Object.entries(raw)
    .map(([label, count]) => ({ label, count: Number(count) }))
    .sort((a, b) => b.count - a.count)

  if (sorted.length <= props.maxBars) return sorted

  const visible = sorted.slice(0, props.maxBars - 1)
  const otherCount = sorted.slice(props.maxBars - 1).reduce((s, i) => s + i.count, 0)
  visible.push({ label: 'Other', count: otherCount })
  return visible
})

const totalLabeled = computed(() =>
  labelItems.value.reduce((s, i) => s + i.count, 0),
)

const activeLabelFilter = computed(() =>
  interaction?.value.state.activeLabelFilter ?? null,
)

function dispatchIntent(intent: SidebarWidgetIntent): void {
  interaction?.value.dispatch(intent)
}

function onChartClick(params: ECElementEvent): void {
  const label = typeof params.name === 'string' ? params.name : null
  if (!label || label === 'Other') {
    return
  }

  const originalEvent = params.event?.event as MouseEvent | undefined
  const operation = originalEvent?.metaKey || originalEvent?.ctrlKey ? 'toggle' : 'replace'

  dispatchIntent({
    type: 'select-labels',
    operation,
    values: [label],
    sourcePanelId: 'label-distribution',
  })
}

function clearActiveFilter(): void {
  dispatchIntent({
    type: 'clear-selection',
    operation: 'clear',
    values: [],
    sourcePanelId: 'label-distribution',
  })
}

// ---------------------------------------------------------------------------
// Chart height — dynamic based on number of bars
// ---------------------------------------------------------------------------

const chartHeight = computed(() => {
  const count = labelItems.value.length
  if (props.orientation === 'horizontal') {
    return Math.max(120, count * 28 + 40)
  }
  return 180
})

// ---------------------------------------------------------------------------
// ECharts option
// ---------------------------------------------------------------------------

const chartOption = computed<EChartsOption>(() => {
  const items = labelItems.value
  const labels = items.map((i) => i.label)
  const values = items.map((i, idx) => ({
    value: i.count,
    itemStyle: {
      color: BAR_COLORS[idx % BAR_COLORS.length],
      opacity: activeLabelFilter.value == null || activeLabelFilter.value === i.label ? 1 : 0.3,
      borderColor: activeLabelFilter.value === i.label ? '#ffffff' : 'transparent',
      borderWidth: activeLabelFilter.value === i.label ? 2 : 0,
    },
  }))

  if (props.orientation === 'horizontal') {
    // Horizontal bars: categories on y-axis, values on x-axis
    return {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter(params: any) {
          const p = Array.isArray(params) ? params[0] : params
          const pct = totalLabeled.value > 0
            ? ((p.value / totalLabeled.value) * 100).toFixed(1)
            : '0'
          return `${p.name}: <b>${p.value}</b> (${pct}%)`
        },
      },
      grid: { left: 4, right: 16, top: 8, bottom: 4, containLabel: true },
      xAxis: {
        type: 'value',
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
        axisLabel: { fontSize: 10, color: 'rgba(255,255,255,0.45)' },
      },
      yAxis: {
        type: 'category',
        data: [...labels].reverse(),
        axisLabel: {
          fontSize: 11,
          color: 'rgba(255,255,255,0.8)',
          width: 70,
          overflow: 'truncate',
        },
        axisTick: { show: false },
        axisLine: { show: false },
      },
      series: [
        {
          type: 'bar',
          data: [...values].reverse(),
          barMaxWidth: 20,
          label: props.showValues
            ? {
                show: true,
                position: 'right',
                fontSize: 10,
                color: 'rgba(255,255,255,0.65)',
                formatter: '{c}',
              }
            : { show: false },
        },
      ],
    }
  }

  // Vertical bars: categories on x-axis, values on y-axis
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter(params: any) {
        const p = Array.isArray(params) ? params[0] : params
        const pct = totalLabeled.value > 0
          ? ((p.value / totalLabeled.value) * 100).toFixed(1)
          : '0'
        return `${p.name}: <b>${p.value}</b> (${pct}%)`
      },
    },
    grid: { left: 4, right: 12, top: 8, bottom: 4, containLabel: true },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: {
        fontSize: 10,
        color: 'rgba(255,255,255,0.8)',
        rotate: labels.length > 6 ? 35 : 0,
      },
      axisTick: { show: false },
      axisLine: { show: false },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      axisLabel: { fontSize: 10, color: 'rgba(255,255,255,0.45)' },
    },
    series: [
      {
        type: 'bar',
        data: values,
        barMaxWidth: 24,
        label: props.showValues
          ? {
              show: true,
              position: 'top',
              fontSize: 10,
              color: 'rgba(255,255,255,0.65)',
              formatter: '{c}',
            }
          : { show: false },
      },
    ],
  }
})
</script>

<template>
  <div class="ldw">
    <!-- Loading -->
    <div v-if="ctx.isLoading && !ctx.stats" class="ldw-loading">
      Loading label data...
    </div>

    <!-- Error -->
    <div v-else-if="ctx.isError" class="ldw-error">
      <span>Failed to load stats</span>
      <button class="ldw-error__retry" @click="ctx.refetch()">Retry</button>
    </div>

    <!-- No labels yet -->
    <div v-else-if="labelItems.length === 0" class="ldw-empty">
      No annotations yet
    </div>

    <!-- Bar chart -->
    <template v-else>
      <div class="ldw-chart" :style="{ height: chartHeight + 'px' }">
        <VChart class="ldw-chart__plot" :option="chartOption" autoresize @click="onChartClick" />
      </div>
      <button
        v-if="activeLabelFilter != null"
        class="ldw-filter-chip"
        @click="clearActiveFilter"
      >
        Filtered by {{ activeLabelFilter }} · Clear
      </button>
      <div class="ldw-summary">
        {{ labelItems.length }} label{{ labelItems.length === 1 ? '' : 's' }} &middot; {{ totalLabeled }} sample{{ totalLabeled === 1 ? '' : 's' }}
      </div>
    </template>
  </div>
</template>

<style scoped>
.ldw {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ldw-loading,
.ldw-empty {
  padding: 20px 0;
  text-align: center;
  color: rgba(255, 255, 255, 0.45);
  font-size: 13px;
}

.ldw-error {
  padding: 16px 0;
  text-align: center;
  color: rgba(255, 160, 100, 0.85);
  font-size: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.ldw-error__retry {
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: rgba(255, 255, 255, 0.7);
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
}

.ldw-error__retry:hover {
  background: rgba(255, 255, 255, 0.14);
}

.ldw-chart {
  width: 100%;
  min-height: 120px;
}

.ldw-chart__plot {
  width: 100%;
  height: 100%;
}

.ldw-filter-chip {
  align-self: center;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 999px;
  color: rgba(255, 255, 255, 0.8);
  cursor: pointer;
  font-size: 11px;
  padding: 4px 10px;
}

.ldw-filter-chip:hover {
  background: rgba(255, 255, 255, 0.14);
}

.ldw-summary {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.45);
  text-align: center;
}
</style>
