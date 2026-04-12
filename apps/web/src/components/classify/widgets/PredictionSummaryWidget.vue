<!--
  PredictionSummaryWidget — sidebar widget for prediction review stats.

  Reads `pr-grid-items` from provide/inject to summarize:
    - Total predictions
    - Edited (draft differs from prediction)
    - Accepted (no draft override)
    - Confidence distribution
-->
<script setup lang="ts">
import { inject, computed, type Ref } from 'vue'
import type { AnnotationGridItem } from '../../../types'

const gridItems = inject<Ref<AnnotationGridItem[]>>('pr-grid-items')

const total = computed(() => gridItems?.value.length ?? 0)

const edited = computed(() =>
  (gridItems?.value ?? []).filter((item) =>
    item.draftLabel != null && item.draftLabel !== item.predictionLabel
  ).length
)

const accepted = computed(() => total.value - edited.value)

const avgConfidence = computed(() => {
  const items = gridItems?.value ?? []
  const withConf = items.filter((i) => i.predictionConfidence != null)
  if (withConf.length === 0) return null
  const sum = withConf.reduce((acc, i) => acc + (i.predictionConfidence ?? 0), 0)
  return sum / withConf.length
})
</script>

<template>
  <div class="psw">
    <div class="psw-row">
      <span class="psw-label">Total</span>
      <span class="psw-value">{{ total }}</span>
    </div>
    <div class="psw-row">
      <span class="psw-label">Accepted</span>
      <span class="psw-value psw-value--ok">{{ accepted }}</span>
    </div>
    <div class="psw-row">
      <span class="psw-label">Edited</span>
      <span class="psw-value psw-value--edit">{{ edited }}</span>
    </div>
    <div v-if="avgConfidence != null" class="psw-row">
      <span class="psw-label">Avg Confidence</span>
      <span class="psw-value">{{ (avgConfidence * 100).toFixed(1) }}%</span>
    </div>
    <div v-if="total === 0" class="psw-empty">No predictions loaded</div>
  </div>
</template>

<style scoped>
.psw {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.psw-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}

.psw-label {
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.5));
}

.psw-value {
  font-weight: 600;
  color: var(--cv-text, #fff);
}

.psw-value--ok {
  color: #4CAF50;
}

.psw-value--edit {
  color: #FF9800;
}

.psw-empty {
  font-size: 12px;
  color: var(--cv-text-disabled, rgba(255, 255, 255, 0.3));
  text-align: center;
  padding: 8px 0;
}
</style>
