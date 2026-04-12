<!--
  SampleViewerWidget — displays sample images/text by ID.

  Inline data shape: { inline: { sampleIds: string[], mode: "grid" | "list" } }

  The widget fetches sample data from the injected classifyDashboard context
  or looks up samples from the parent view.  For simplicity, it renders image
  URIs directly (resolved via imageAdapters).

  Config props:
    thumbSize — thumbnail size in px (default 80)
-->
<script setup lang="ts">
import { computed, inject } from 'vue'
import { resolveImageUris } from '../../../utils/imageAdapters'

const props = defineProps<{
  data?: Record<string, unknown> | null
  config?: Record<string, unknown>
  size?: 'compact' | 'normal' | 'large'
}>()

const thumbSize = computed(() => Number(props.config?.thumbSize ?? 80))

interface SampleViewerData {
  sampleIds: string[]
  mode: 'grid' | 'list'
  /** Optional pre-fetched sample objects with image_uris */
  samples?: Array<{ id: string; image_uris: string[]; label?: string }>
}

const viewerData = computed<SampleViewerData | null>(() => {
  if (!props.data) return null
  const raw = (props.data as Record<string, unknown>).inline ?? props.data
  if (!raw || typeof raw !== 'object') return null
  const d = raw as Record<string, unknown>
  const sampleIds = d.sampleIds ?? d.sample_ids ?? []
  if (!Array.isArray(sampleIds)) return null
  return {
    sampleIds: sampleIds as string[],
    mode: (d.mode as 'grid' | 'list') ?? 'grid',
    samples: d.samples as SampleViewerData['samples'],
  }
})

const samples = computed(() => {
  if (!viewerData.value) return []
  // If pre-fetched samples are provided, use them
  if (viewerData.value.samples && viewerData.value.samples.length > 0) {
    return viewerData.value.samples
  }
  // Otherwise just show IDs as placeholders
  return viewerData.value.sampleIds.map(id => ({ id, image_uris: [] as string[], label: undefined }))
})

function resolveThumb(uris: string[]): string {
  if (!uris || uris.length === 0) return ''
  const resolved = resolveImageUris(uris)
  return resolved[0] || ''
}
</script>

<template>
  <div class="svw">
    <div v-if="!viewerData || samples.length === 0" class="svw-empty">No samples to display</div>
    <div v-else :class="viewerData.mode === 'grid' ? 'svw-grid' : 'svw-list'">
      <div
        v-for="s in samples"
        :key="s.id"
        class="svw-item"
      >
        <img
          v-if="resolveThumb(s.image_uris)"
          :src="resolveThumb(s.image_uris)"
          :style="{ width: thumbSize + 'px', height: thumbSize + 'px' }"
          class="svw-img"
        />
        <div v-else class="svw-placeholder" :style="{ width: thumbSize + 'px', height: thumbSize + 'px' }">
          {{ s.id.slice(0, 6) }}
        </div>
        <div v-if="s.label" class="svw-label">{{ s.label }}</div>
      </div>
    </div>
    <div v-if="viewerData" class="svw-footer">{{ samples.length }} sample(s)</div>
  </div>
</template>

<style scoped>
.svw {
  width: 100%;
}
.svw-empty {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.4);
  padding: 12px 0;
  text-align: center;
}
.svw-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.svw-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.svw-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
.svw-list .svw-item {
  flex-direction: row;
  gap: 8px;
}
.svw-img {
  object-fit: cover;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.05);
}
.svw-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.3);
  font-size: 9px;
  font-family: monospace;
}
.svw-label {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.6);
  text-align: center;
}
.svw-footer {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.35);
  padding: 4px 0 0;
  text-align: right;
}
</style>
