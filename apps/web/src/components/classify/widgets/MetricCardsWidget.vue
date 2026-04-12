<!--
  MetricCardsWidget — KPI card grid.

  Inline data shape: { inline: { metrics: [{ label, value, color? }] } }

  Config props:
    columns — grid columns (default 2)
-->
<script setup lang="ts">
import { computed } from 'vue'
import type { MetricCardItem } from '../../../types'

const props = defineProps<{
  data?: Record<string, unknown> | null
  config?: Record<string, unknown>
  size?: 'compact' | 'normal' | 'large'
}>()

const columns = computed(() => Number(props.config?.columns ?? 2))

const metrics = computed<MetricCardItem[]>(() => {
  if (!props.data) return []
  const raw = (props.data as Record<string, unknown>).inline ?? props.data
  if (!raw || typeof raw !== 'object') return []
  const arr = (raw as Record<string, unknown>).metrics
  if (!Array.isArray(arr)) return []
  return arr as MetricCardItem[]
})
</script>

<template>
  <div class="mcw">
    <div v-if="metrics.length === 0" class="mcw-empty">No metrics</div>
    <div v-else class="mcw-grid" :style="{ gridTemplateColumns: `repeat(${columns}, 1fr)` }">
      <div v-for="(m, i) in metrics" :key="i" class="mcw-card">
        <div class="mcw-value" :style="m.color ? { color: m.color } : {}">{{ m.value }}</div>
        <div class="mcw-label">{{ m.label }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mcw {
  width: 100%;
}
.mcw-empty {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.4);
  padding: 12px 0;
  text-align: center;
}
.mcw-grid {
  display: grid;
  gap: 6px;
}
.mcw-card {
  background: rgba(255, 255, 255, 0.04);
  border-radius: 6px;
  padding: 8px 10px;
  text-align: center;
}
.mcw-value {
  font-size: 18px;
  font-weight: 700;
  color: #fff;
  line-height: 1.2;
}
.mcw-label {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.5);
  margin-top: 2px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
</style>
