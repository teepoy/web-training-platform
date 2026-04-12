<!--
  MarkdownLogWidget — scrollable log panel with timestamp + level badges.

  Inline data shape: { inline: { entries: [{ ts, level, message }] } }

  Config props:
    maxEntries — cap visible entries (default 50)
    autoScroll — keep pinned to bottom (default true)
-->
<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import type { MarkdownLogEntry } from '../../../types'

const props = defineProps<{
  data?: Record<string, unknown> | null
  config?: Record<string, unknown>
  size?: 'compact' | 'normal' | 'large'
}>()

const containerRef = ref<HTMLElement | null>(null)

const maxEntries = computed(() => Number(props.config?.maxEntries ?? 50))
const autoScroll = computed(() => props.config?.autoScroll !== false)

const entries = computed<MarkdownLogEntry[]>(() => {
  if (!props.data) return []
  const raw = (props.data as Record<string, unknown>).inline ?? props.data
  if (!raw || typeof raw !== 'object') return []
  const arr = (raw as Record<string, unknown>).entries
  if (!Array.isArray(arr)) return []
  return arr.slice(-maxEntries.value) as MarkdownLogEntry[]
})

const containerHeight = computed(() => {
  switch (props.size) {
    case 'compact': return '120px'
    case 'large': return '280px'
    default: return '180px'
  }
})

function levelClass(level: string): string {
  const l = level.toLowerCase()
  if (l === 'error' || l === 'err') return 'mlw-badge--error'
  if (l === 'warn' || l === 'warning') return 'mlw-badge--warn'
  if (l === 'info') return 'mlw-badge--info'
  return 'mlw-badge--debug'
}

watch(entries, async () => {
  if (autoScroll.value && containerRef.value) {
    await nextTick()
    containerRef.value.scrollTop = containerRef.value.scrollHeight
  }
})
</script>

<template>
  <div class="mlw">
    <div v-if="entries.length === 0" class="mlw-empty">No log entries</div>
    <div v-else ref="containerRef" class="mlw-scroll" :style="{ maxHeight: containerHeight }">
      <div v-for="(entry, i) in entries" :key="i" class="mlw-entry">
        <span class="mlw-ts">{{ entry.ts }}</span>
        <span class="mlw-badge" :class="levelClass(entry.level)">{{ entry.level }}</span>
        <span class="mlw-msg">{{ entry.message }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mlw {
  width: 100%;
}
.mlw-empty {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.4);
  padding: 12px 0;
  text-align: center;
}
.mlw-scroll {
  overflow-y: auto;
  font-family: monospace;
  font-size: 11px;
  line-height: 1.5;
}
.mlw-entry {
  display: flex;
  gap: 6px;
  align-items: baseline;
  padding: 1px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}
.mlw-ts {
  color: rgba(255, 255, 255, 0.35);
  white-space: nowrap;
  flex-shrink: 0;
  font-size: 10px;
}
.mlw-badge {
  display: inline-block;
  padding: 0 4px;
  border-radius: 3px;
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  flex-shrink: 0;
}
.mlw-badge--error { background: rgba(244, 67, 54, 0.3); color: #ef9a9a; }
.mlw-badge--warn { background: rgba(255, 152, 0, 0.3); color: #ffcc80; }
.mlw-badge--info { background: rgba(33, 150, 243, 0.25); color: #90caf9; }
.mlw-badge--debug { background: rgba(255, 255, 255, 0.08); color: rgba(255, 255, 255, 0.5); }
.mlw-msg {
  color: rgba(255, 255, 255, 0.75);
  word-break: break-word;
}
</style>
