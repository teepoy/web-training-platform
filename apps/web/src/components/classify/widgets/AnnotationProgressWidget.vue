<!--
  AnnotationProgressWidget — donut chart + metric cards for annotation progress.

  Accepted props (via sidebarConfig descriptor):
    chartType        'donut' | 'bar'   — visualisation style (default 'donut')
    showCounts       boolean            — show absolute counts (default true)
    showPercent      boolean            — show % in donut centre (default true)
    includeDrafts    boolean            — add draft slice to chart (default true)
    showLabelBreakdown boolean          — per-label table below chart (default true)

  Data comes from the injected ClassifyDashboardContext.
-->
<script setup lang="ts">
import { computed, inject } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { PieChart, BarChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'
import type { ClassifyDashboardContext } from '../../../composables/useClassifyDashboard'

use([CanvasRenderer, GridComponent, LegendComponent, PieChart, BarChart, TooltipComponent])

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

const props = withDefaults(defineProps<{
  chartType?: 'donut' | 'bar'
  showCounts?: boolean
  showPercent?: boolean
  includeDrafts?: boolean
  showLabelBreakdown?: boolean
}>(), {
  chartType: 'donut',
  showCounts: true,
  showPercent: true,
  includeDrafts: true,
  showLabelBreakdown: true,
})

// ---------------------------------------------------------------------------
// Injected context
// ---------------------------------------------------------------------------

const ctx = inject<ClassifyDashboardContext>('classifyDashboard')!

// ---------------------------------------------------------------------------
// Derived data
// ---------------------------------------------------------------------------

const total = computed(() => ctx.stats?.total_samples ?? 0)
const annotated = computed(() => ctx.stats?.annotated_samples ?? 0)
const unlabeled = computed(() => ctx.stats?.unlabeled_samples ?? 0)
const draftCount = computed(() => ctx.draftCount)
const selectedCount = computed(() => ctx.selectedCount)

const annotatedPercent = computed(() =>
  total.value > 0 ? Math.round((annotated.value / total.value) * 100) : 0,
)

const labelCounts = computed<Array<{ label: string; count: number }>>(() => {
  const raw = ctx.stats?.label_counts ?? {}
  return Object.entries(raw)
    .map(([label, count]) => ({ label, count: Number(count) }))
    .sort((a, b) => b.count - a.count)
})

// ---------------------------------------------------------------------------
// Chart colours
// ---------------------------------------------------------------------------

const COLORS = {
  annotated: '#63e2b7',
  remaining: '#e2e3e5',
  draft: '#f0a020',
}

const LABEL_COLORS = [
  '#4CAF50', '#2196F3', '#FF9800', '#E91E63', '#9C27B0',
  '#00BCD4', '#FF5722', '#795548', '#607D8B', '#CDDC39',
]

// ---------------------------------------------------------------------------
// Donut chart option
// ---------------------------------------------------------------------------

const donutOption = computed<EChartsOption>(() => {
  const remaining = props.includeDrafts
    ? Math.max(0, unlabeled.value - draftCount.value)
    : unlabeled.value
  const draftSlice = props.includeDrafts ? draftCount.value : 0

  const data: Array<{ value: number; name: string; itemStyle: { color: string } }> = []

  if (annotated.value > 0) {
    data.push({ value: annotated.value, name: 'Annotated', itemStyle: { color: COLORS.annotated } })
  }
  if (draftSlice > 0) {
    data.push({ value: draftSlice, name: 'Drafts', itemStyle: { color: COLORS.draft } })
  }
  if (remaining > 0) {
    data.push({ value: remaining, name: 'Remaining', itemStyle: { color: COLORS.remaining } })
  }

  // Empty dataset placeholder
  if (data.length === 0) {
    data.push({ value: 1, name: 'No data', itemStyle: { color: COLORS.remaining } })
  }

  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    series: [
      {
        type: 'pie',
        radius: ['55%', '80%'],
        center: ['50%', '50%'],
        avoidLabelOverlap: false,
        label: {
          show: props.showPercent,
          position: 'center',
          formatter: `${annotatedPercent.value}%`,
          fontSize: 22,
          fontWeight: 'bold',
          color: '#ffffffdd',
        },
        labelLine: { show: false },
        data,
      },
    ],
  }
})

// ---------------------------------------------------------------------------
// Bar chart option (label breakdown)
// ---------------------------------------------------------------------------

const barOption = computed<EChartsOption>(() => {
  const items = labelCounts.value
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 4, right: 12, top: 8, bottom: 4, containLabel: true },
    xAxis: { type: 'value', splitLine: { lineStyle: { opacity: 0.12 } } },
    yAxis: {
      type: 'category',
      data: items.map((i) => i.label),
      axisLabel: { fontSize: 11, color: '#ffffffcc' },
    },
    series: [
      {
        type: 'bar',
        data: items.map((i, idx) => ({
          value: i.count,
          itemStyle: { color: LABEL_COLORS[idx % LABEL_COLORS.length] },
        })),
        barMaxWidth: 18,
      },
    ],
  }
})
</script>

<template>
  <div class="apw">
    <!-- Loading state -->
    <div v-if="ctx.isLoading && !ctx.stats" class="apw-loading">
      Loading stats...
    </div>

    <!-- Error state -->
    <div v-else-if="ctx.isError" class="apw-error">
      <span>Failed to load stats</span>
      <button class="apw-error__retry" @click="ctx.refetch()">Retry</button>
    </div>

    <template v-else>
      <!-- Donut chart -->
      <div v-if="chartType === 'donut'" class="apw-chart">
        <VChart class="apw-chart__plot" :option="donutOption" autoresize />
      </div>

      <!-- Metric cards -->
      <div v-if="showCounts" class="apw-metrics">
        <div class="apw-metric">
          <span class="apw-metric__value" style="color: #63e2b7">{{ annotated }}</span>
          <span class="apw-metric__label">Annotated</span>
        </div>
        <div class="apw-metric">
          <span class="apw-metric__value" style="color: #e2e3e5">{{ unlabeled }}</span>
          <span class="apw-metric__label">Remaining</span>
        </div>
        <div class="apw-metric">
          <span class="apw-metric__value">{{ total }}</span>
          <span class="apw-metric__label">Total</span>
        </div>
        <div v-if="includeDrafts && draftCount > 0" class="apw-metric">
          <span class="apw-metric__value" style="color: #f0a020">{{ draftCount }}</span>
          <span class="apw-metric__label">Drafts</span>
        </div>
        <div v-if="selectedCount > 0" class="apw-metric">
          <span class="apw-metric__value" style="color: #70c0e8">{{ selectedCount }}</span>
          <span class="apw-metric__label">Selected</span>
        </div>
      </div>

      <!-- Label breakdown -->
      <div v-if="showLabelBreakdown && labelCounts.length > 0" class="apw-labels">
        <div class="apw-labels__title">Labels</div>

        <!-- Bar chart mode -->
        <div v-if="chartType === 'bar'" class="apw-barchart">
          <VChart
            class="apw-barchart__plot"
            :option="barOption"
            autoresize
          />
        </div>

        <!-- Default: compact list -->
        <div v-else class="apw-labels__list">
          <div
            v-for="(item, idx) in labelCounts"
            :key="item.label"
            class="apw-labels__row"
          >
            <span
              class="apw-labels__dot"
              :style="{ background: LABEL_COLORS[idx % LABEL_COLORS.length] }"
            />
            <span class="apw-labels__name">{{ item.label }}</span>
            <span class="apw-labels__count">{{ item.count }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.apw {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.apw-loading {
  padding: 24px 0;
  text-align: center;
  color: rgba(255, 255, 255, 0.45);
  font-size: 13px;
}

.apw-error {
  padding: 16px 0;
  text-align: center;
  color: rgba(255, 160, 100, 0.85);
  font-size: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.apw-error__retry {
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: rgba(255, 255, 255, 0.7);
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
}

.apw-error__retry:hover {
  background: rgba(255, 255, 255, 0.14);
}

.apw-chart {
  width: 100%;
  aspect-ratio: 1 / 1;
  max-height: 200px;
}

.apw-chart__plot {
  width: 100%;
  height: 100%;
}

.apw-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.apw-metric {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 6px 0;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.04);
}

.apw-metric__value {
  font-size: 18px;
  font-weight: 700;
  line-height: 1.2;
}

.apw-metric__label {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.5);
  margin-top: 2px;
}

.apw-labels {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.apw-labels__title {
  font-size: 12px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.65);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.apw-labels__list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.apw-labels__row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.04);
  font-size: 12px;
}

.apw-labels__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.apw-labels__name {
  flex: 1;
  color: rgba(255, 255, 255, 0.85);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.apw-labels__count {
  font-weight: 600;
  color: rgba(255, 255, 255, 0.7);
}

.apw-barchart {
  width: 100%;
  height: 150px;
}

.apw-barchart__plot {
  width: 100%;
  height: 100%;
}
</style>
