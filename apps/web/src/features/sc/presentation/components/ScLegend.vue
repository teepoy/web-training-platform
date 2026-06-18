<script setup lang="ts">
import { computed } from 'vue'
import { NColorPicker, NTag } from 'naive-ui'
import {
  parsePoints,
  groupByClass,
  groupByBin,
  binColor,
  classColor,
  legendColor,
} from './scMapUtils'
import type { DefectList } from '../../generated/proto/sc/v1/sample_pb'

type LegendSource = 'class' | 'bin' | 'annotation' | 'prediction'
type LegendKey = number | string
const UNLABELED_KEY = '__unlabeled__'
const NO_PREDICTION_KEY = '__no_prediction__'

const props = defineProps<{
  points?: number[]
  fullPoints?: number[]
  selectedClassNumber?: LegendKey | null
  legendSource?: LegendSource
  classNumbers?: Record<string, DefectList>
  roughBins?: Record<string, DefectList>
  annotations?: Record<string, DefectList>
  predictions?: Record<string, DefectList>
  colorMap?: Record<string, string>
}>()

const emit = defineEmits<{
  (e: 'select-class', key: LegendKey | null): void
  (e: 'update:colorMap', colorMap: Record<string, string>): void
}>()

function sortLegendKeys(keys: string[]): string[] {
  return [...keys].sort((a, b) =>
    String(a).localeCompare(String(b), undefined, { numeric: true }),
  )
}

function colorMapKeyForLegendKey(source: LegendSource, rawKey: string, compactGroups?: Record<string, DefectList>): string {
  if (source === 'class' || source === 'bin' || !compactGroups) return rawKey
  if (rawKey === UNLABELED_KEY || rawKey === NO_PREDICTION_KEY) return '-1'
  return String(
    sortLegendKeys(Object.keys(compactGroups).filter(
      (key) => key !== UNLABELED_KEY && key !== NO_PREDICTION_KEY,
    )).indexOf(rawKey),
  )
}

const legendData = computed(() => {
  const source = props.legendSource ?? 'class'
  const compactGroups = {
    class: props.classNumbers,
    bin: props.roughBins,
    annotation: props.annotations,
    prediction: props.predictions,
  }[source]
  const isNumericSource = source === 'class' || source === 'bin'
  const colorFn = source === 'bin' ? binColor : classColor
  const labelPrefix = source === 'class' ? 'Class ' : source === 'bin' ? 'Bin ' : ''
  const missingLabels: Record<string, string> = {
    [UNLABELED_KEY]: 'Unlabeled',
    [NO_PREDICTION_KEY]: 'No Prediction',
  }
  if (compactGroups && Object.keys(compactGroups).length > 0) {
    return Object.entries(compactGroups)
      .map(([rawKey, group]) => {
        const key = isNumericSource ? Number(rawKey) : rawKey
        const colorKey = colorMapKeyForLegendKey(source, rawKey, compactGroups)
        return {
          key,
          colorKey,
          count: group.count,
          color: props.colorMap?.[colorKey] ?? legendColor(source, rawKey),
          label: missingLabels[rawKey] ?? (labelPrefix + rawKey),
        }
      })
      .filter((item) => typeof item.key === 'string' || Number.isFinite(item.key))
      .sort((a, b) => String(a.key).localeCompare(String(b.key), undefined, { numeric: true }))
  }

  if (!isNumericSource) return []

  const dataToParse = props.fullPoints || props.points || []
  if (dataToParse.length === 0) return []

  const parsed = parsePoints(dataToParse)
  const grouped = source === 'bin' ? groupByBin(parsed) : groupByClass(parsed)

  return Array.from(grouped.entries())
    .map(([key, pts]) => ({
      key,
      colorKey: String(key),
      count: pts.length,
      color: props.colorMap?.[String(key)] ?? colorFn(key),
      label: labelPrefix + key,
    }))
    .sort((a, b) => a.key - b.key)
})

const handleSelect = (key: LegendKey) => {
  if (props.selectedClassNumber === key) {
    emit('select-class', null)
  } else {
    emit('select-class', key)
  }
}

const handleColorUpdate = (key: string, color: string) => {
  emit('update:colorMap', {
    ...(props.colorMap ?? {}),
    [key]: color,
  })
}
</script>

<template>
  <div class="sc-legend">
    <div v-if="legendData.length > 0" class="sc-legend-list" data-testid="sc-legend-list">
      <div
        v-for="item in legendData"
        :key="item.key"
        class="sc-legend-item"
        :class="{ '--selected': props.selectedClassNumber === item.key }"
        :style="props.selectedClassNumber === item.key ? { borderLeft: `3px solid ${item.color}` } : { borderLeft: '3px solid transparent' }"
        :data-testid="`sc-legend-class-${item.key}`"
        @click="handleSelect(item.key)"
      >
        <span
          class="sc-legend-color-picker"
          :data-testid="`sc-legend-color-${item.key}`"
          @click.stop
        >
          <NColorPicker
            :value="item.color"
            :show-alpha="false"
            size="small"
            :modes="['hex']"
            @update:value="(value) => handleColorUpdate(item.colorKey, value)"
          />
        </span>
        <span class="sc-legend-label">{{ item.label }}</span>
        <NTag size="small" :bordered="false" style="font-size: 10px;">{{ item.count }}</NTag>
      </div>
    </div>
    <div v-else class="sc-legend-empty" data-testid="sc-legend-empty">
      No classes
    </div>
  </div>
</template>

<style scoped>
.sc-legend {
  padding: 4px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}
.sc-legend-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.sc-legend-empty {
  padding: 8px 4px;
  color: var(--n-text-color-disabled, rgba(0, 0, 0, 0.38));
  font-size: 11px;
}
.sc-legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 4px;
  cursor: pointer;
  border-radius: 4px;
  transition: background-color 0.2s, border-left 0.2s;
}
.sc-legend-item:hover {
  background-color: var(--n-color-hover, rgba(0, 0, 0, 0.05));
}
.sc-legend-item.--selected {
  background-color: var(--n-color-pressed, rgba(0, 0, 0, 0.1));
}
.sc-legend-color-picker {
  display: inline-flex;
  flex-shrink: 0;
  width: 18px;
}
.sc-legend-color-picker :deep(.n-color-picker-trigger) {
  border-radius: 50%;
  height: 12px;
  min-height: 12px;
  padding: 0;
  width: 12px;
}
.sc-legend-color-picker :deep(.n-color-picker-trigger__fill) {
  border-radius: 50%;
}
.sc-legend-color-picker :deep(.n-color-picker-trigger__value) {
  display: none;
}
.sc-legend-label {
  flex-grow: 1;
  font-size: 11px;
}
</style>
