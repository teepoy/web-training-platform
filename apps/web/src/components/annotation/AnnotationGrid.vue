<!--
  AnnotationGrid — shared card-grid component for ClassifyView & PredictionReviewView.

  Features:
    - Virtual scrolling (TanStack Virtual) for large datasets
    - Vertical label panel (search + scrollable label list + add button)
    - Rubber-band multi-select with auto-scroll (distinct / continuous modes)
    - Keyboard shortcuts (1-9 for labels)
    - Floating bottom bar (filter/sort slot on left, selection count + submit on right)

  Props:
    items            — AnnotationGridItem[]  (the data to render)
    totalCount       — number                (total items, for "loaded X of Y")
    labelSpace       — string[]              (available labels)
    thumbSize        — number                (card image height, default 160)
    isLoading        — boolean               (show loading indicator)
    submitting       — boolean               (submit button loading state)
    showAddLabel     — boolean               (show "+ Add label" in panel, default true)

  Events:
    select           — (ids: Set<string>)
    apply-label      — ({ ids: string[], label: string })
    submit           — ()
    load-more        — ()
    add-label        — (name: string)

  Slots:
    bar-left         — extra controls in the floating bottom bar left side
-->
<template>
  <div class="ag" @keydown="onKeyDown" tabindex="-1">
    <!-- Label panel (left) -->
    <div class="ag-label-panel">
      <input
        v-model="labelSearch"
        class="ag-label-search"
        placeholder="Search labels..."
        @keydown.stop
      />
      <div class="ag-label-list">
        <div
          v-for="(label, idx) in filteredLabels"
          :key="label"
          class="ag-label-item"
          :class="{ 'ag-label-item--active': false }"
          @click="applyLabelToSelection(label)"
          :title="label"
        >
          <span class="ag-label-dot" :style="{ background: labelColor(label) }" />
          <span class="ag-label-name">{{ label }}</span>
          <span v-if="idx < 9" class="ag-label-shortcut">{{ idx + 1 }}</span>
        </div>
      </div>
      <button
        v-if="showAddLabel"
        class="ag-label-add"
        @click="emit('add-label', '')"
      >
        + Add label
      </button>
    </div>

    <!-- Card grid (right) -->
    <div class="ag-grid-area">
      <div
        ref="scrollRef"
        class="ag-scroll-container"
        @mousedown="onMouseDown"
        @scroll="onContainerScroll"
      >
        <div
          :style="{ height: virtualizer.getTotalSize() + 'px', position: 'relative', width: '100%' }"
        >
          <div
            v-for="vRow in virtualizer.getVirtualItems()"
            :key="vRow.index"
            :style="{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: vRow.size + 'px',
              transform: `translateY(${vRow.start}px)`,
            }"
          >
            <div class="ag-card-row">
              <div
                v-for="item in getRowItems(vRow.index)"
                :key="item.id"
                class="ag-card"
                :class="{
                  'ag-card--selected': selectedIds.has(item.id),
                  'ag-card--draft': !!(item.draftLabel || item.predictionLabel),
                }"
                :style="{ width: cardWidth + 'px' }"
                :data-item-id="item.id"
                @click.stop="onCardClick(item.id, $event)"
              >
                <div class="ag-card-images" :style="{ height: thumbSize + 'px' }">
                  <img
                    v-for="(src, imgIdx) in item.imageSrcs"
                    :key="imgIdx"
                    :src="src"
                    loading="lazy"
                    alt=""
                    class="ag-card-img"
                    :style="{ height: thumbSize + 'px' }"
                  />
                </div>
                <div class="ag-card-footer">
                  <span
                    v-if="effectiveLabel(item)"
                    class="ag-badge"
                    :style="{ background: labelColor(effectiveLabel(item)!) }"
                  >{{ effectiveLabel(item) }}</span>
                  <span v-else class="ag-badge ag-badge--empty">&mdash;</span>
                  <span
                    v-if="item.predictionConfidence != null"
                    class="ag-confidence"
                  >{{ (item.predictionConfidence * 100).toFixed(0) }}%</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Rubber band overlay -->
        <div
          v-if="isDragging && rubberRect"
          class="ag-rubber-band"
          :style="{
            left: rubberRect.left + 'px',
            top: rubberRect.top + 'px',
            width: rubberRect.width + 'px',
            height: rubberRect.height + 'px',
          }"
        />

        <!-- Loading indicator -->
        <div v-if="isLoading" class="ag-loading">Loading more...</div>
      </div>

      <!-- Floating bottom bar -->
      <div class="ag-bottom-bar">
        <div class="ag-bar-left">
          <slot name="bar-left" />
        </div>
        <div class="ag-bar-right">
          <span class="ag-bar-count">
            {{ selectedIds.size }} selected &middot; {{ items.length }} of {{ totalCount }} loaded
          </span>
          <button
            class="ag-submit-btn"
            :disabled="submitting || draftCount === 0"
            @click="emit('submit')"
          >
            {{ submitting ? 'Submitting...' : `Submit ${draftCount}` }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useVirtualizer } from '@tanstack/vue-virtual'
import type { AnnotationGridItem } from '../../types'

// ---------------------------------------------------------------------------
// Props / Events
// ---------------------------------------------------------------------------

const props = withDefaults(defineProps<{
  items: AnnotationGridItem[]
  totalCount: number
  labelSpace: string[]
  thumbSize?: number
  isLoading?: boolean
  submitting?: boolean
  showAddLabel?: boolean
}>(), {
  thumbSize: 160,
  isLoading: false,
  submitting: false,
  showAddLabel: true,
})

const emit = defineEmits<{
  select: [ids: Set<string>]
  'apply-label': [payload: { ids: string[]; label: string }]
  submit: []
  'load-more': []
  'add-label': [name: string]
}>()

// ---------------------------------------------------------------------------
// Colors
// ---------------------------------------------------------------------------

const LABEL_COLORS = [
  '#4CAF50', '#2196F3', '#FF9800', '#E91E63', '#9C27B0',
  '#00BCD4', '#FF5722', '#795548', '#607D8B', '#CDDC39',
]

function labelColor(label: string): string {
  const idx = props.labelSpace.indexOf(label)
  if (idx === -1) return '#9E9E9E'
  return LABEL_COLORS[idx % LABEL_COLORS.length]
}

function effectiveLabel(item: AnnotationGridItem): string | null {
  return item.draftLabel ?? item.predictionLabel ?? item.currentLabel ?? null
}

// ---------------------------------------------------------------------------
// Label panel
// ---------------------------------------------------------------------------

const labelSearch = ref('')

const filteredLabels = computed(() => {
  if (!labelSearch.value) return props.labelSpace
  const q = labelSearch.value.toLowerCase()
  return props.labelSpace.filter((l) => l.toLowerCase().includes(q))
})

// ---------------------------------------------------------------------------
// Grid layout
// ---------------------------------------------------------------------------

const scrollRef = ref<HTMLElement | null>(null)
const containerWidth = ref(800)
const cardWidth = computed(() => props.thumbSize + 20)
const cardsPerRow = computed(() => Math.max(1, Math.floor(containerWidth.value / cardWidth.value)))
const rowCount = computed(() => Math.ceil(props.items.length / cardsPerRow.value))

function getRowItems(rowIndex: number): AnnotationGridItem[] {
  const start = rowIndex * cardsPerRow.value
  return props.items.slice(start, start + cardsPerRow.value)
}

// ---------------------------------------------------------------------------
// Selection
// ---------------------------------------------------------------------------

const selectedIds = ref<Set<string>>(new Set())

const draftCount = computed(() =>
  props.items.filter((item) => item.draftLabel != null).length
)

function onCardClick(id: string, e: MouseEvent) {
  if (wasDragging) return
  if (e.ctrlKey || e.metaKey) {
    const next = new Set(selectedIds.value)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    selectedIds.value = next
  } else {
    selectedIds.value = new Set([id])
  }
  emit('select', selectedIds.value)
}

function applyLabelToSelection(label: string) {
  if (selectedIds.value.size === 0) return
  emit('apply-label', { ids: [...selectedIds.value], label })
}

// ---------------------------------------------------------------------------
// Keyboard shortcuts (1-9 for labels)
// ---------------------------------------------------------------------------

function onKeyDown(e: KeyboardEvent) {
  const el = document.activeElement
  if (
    el instanceof HTMLInputElement ||
    el instanceof HTMLSelectElement ||
    el instanceof HTMLTextAreaElement ||
    (el instanceof HTMLElement && el.isContentEditable)
  ) return

  const num = parseInt(e.key, 10)
  if (isNaN(num) || num < 1 || num > 9) return
  const label = props.labelSpace[num - 1]
  if (!label) return
  if (selectedIds.value.size === 0) return
  e.preventDefault()
  applyLabelToSelection(label)
}

// ---------------------------------------------------------------------------
// Virtualizer
// ---------------------------------------------------------------------------

const rowHeight = computed(() => props.thumbSize + 48)

const virtualizer = useVirtualizer({
  get count() { return rowCount.value },
  getScrollElement: () => scrollRef.value,
  estimateSize: () => rowHeight.value,
  overscan: 3,
})

// Trigger load-more when scrolling near the bottom
function onContainerScroll() {
  const el = scrollRef.value
  if (!el) return
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 200) {
    emit('load-more')
  }
}

// Watch virtual items for load-more
watch(
  () => virtualizer.value.getVirtualItems(),
  (items) => {
    if (!items.length) return
    const lastItem = items[items.length - 1]
    if (lastItem && lastItem.index >= rowCount.value - 2) {
      emit('load-more')
    }
  },
)

// ---------------------------------------------------------------------------
// Rubber-band selection
// ---------------------------------------------------------------------------

const isDragging = ref(false)
const dragStart = ref<{ x: number; y: number } | null>(null)
const dragCurrent = ref<{ x: number; y: number } | null>(null)
const DRAG_THRESHOLD = 5
let wasDragging = false
let dragCtrlHeld = false
let autoScrollTimer: ReturnType<typeof setInterval> | null = null

const rubberRect = computed(() => {
  if (!dragStart.value || !dragCurrent.value || !scrollRef.value) return null
  const rect = scrollRef.value.getBoundingClientRect()
  const x1 = Math.min(dragStart.value.x, dragCurrent.value.x) - rect.left
  const y1 = Math.min(dragStart.value.y, dragCurrent.value.y) - rect.top + scrollRef.value.scrollTop
  const x2 = Math.max(dragStart.value.x, dragCurrent.value.x) - rect.left
  const y2 = Math.max(dragStart.value.y, dragCurrent.value.y) - rect.top + scrollRef.value.scrollTop
  return { left: x1, top: y1, width: x2 - x1, height: y2 - y1 }
})

function onMouseDown(e: MouseEvent) {
  if (e.button !== 0) return
  if ((e.target as HTMLElement).closest('.ag-label-panel, .ag-bottom-bar, .ag-label-search, button, input')) return
  e.preventDefault()
  dragStart.value = { x: e.clientX, y: e.clientY }
  dragCurrent.value = { x: e.clientX, y: e.clientY }
  dragCtrlHeld = e.ctrlKey || e.metaKey
  document.addEventListener('mousemove', onDocMouseMove)
  document.addEventListener('mouseup', onDocMouseUp)
}

function onDocMouseMove(e: MouseEvent) {
  if (!dragStart.value) return
  dragCurrent.value = { x: e.clientX, y: e.clientY }
  const dx = e.clientX - dragStart.value.x
  const dy = e.clientY - dragStart.value.y
  if (!isDragging.value && Math.sqrt(dx * dx + dy * dy) >= DRAG_THRESHOLD) {
    isDragging.value = true
    startAutoScroll()
  }
  if (isDragging.value) {
    updateRubberBandSelection()
  }
}

function onDocMouseUp() {
  document.removeEventListener('mousemove', onDocMouseMove)
  document.removeEventListener('mouseup', onDocMouseUp)
  stopAutoScroll()

  if (isDragging.value) {
    updateRubberBandSelection()
    wasDragging = true
    setTimeout(() => { wasDragging = false }, 0)
  }

  isDragging.value = false
  dragStart.value = null
  dragCurrent.value = null
}

function updateRubberBandSelection() {
  if (!rubberRect.value || !scrollRef.value) return
  const rr = rubberRect.value
  const rrBottom = rr.top + rr.height

  // Find all card elements that intersect the rubber band
  const cards = scrollRef.value.querySelectorAll<HTMLElement>('[data-item-id]')
  const intersecting: string[] = []
  const containerRect = scrollRef.value.getBoundingClientRect()
  const scrollTop = scrollRef.value.scrollTop

  for (const card of cards) {
    const cardRect = card.getBoundingClientRect()
    const cardTop = cardRect.top - containerRect.top + scrollTop
    const cardBottom = cardTop + cardRect.height
    const cardLeft = cardRect.left - containerRect.left
    const cardRight = cardLeft + cardRect.width

    if (cardBottom >= rr.top && cardTop <= rrBottom && cardRight >= rr.left && cardLeft <= rr.left + rr.width) {
      const id = card.dataset.itemId
      if (id) intersecting.push(id)
    }
  }

  if (dragCtrlHeld) {
    const next = new Set(selectedIds.value)
    intersecting.forEach((id) => next.add(id))
    selectedIds.value = next
  } else {
    selectedIds.value = new Set(intersecting)
  }
  emit('select', selectedIds.value)
}

// Auto-scroll when drag reaches viewport edges
function startAutoScroll() {
  if (autoScrollTimer) return
  autoScrollTimer = setInterval(() => {
    if (!isDragging.value || !dragCurrent.value || !scrollRef.value) return
    const rect = scrollRef.value.getBoundingClientRect()
    const edgeZone = 40
    const speed = 12
    if (dragCurrent.value.y < rect.top + edgeZone) {
      scrollRef.value.scrollTop -= speed
    } else if (dragCurrent.value.y > rect.bottom - edgeZone) {
      scrollRef.value.scrollTop += speed
    }
  }, 16)
}

function stopAutoScroll() {
  if (autoScrollTimer) {
    clearInterval(autoScrollTimer)
    autoScrollTimer = null
  }
}

// ---------------------------------------------------------------------------
// Container resize observer
// ---------------------------------------------------------------------------

let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  if (scrollRef.value) {
    containerWidth.value = scrollRef.value.clientWidth
    resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        containerWidth.value = entry.contentRect.width
      }
    })
    resizeObserver.observe(scrollRef.value)
  }
})

onUnmounted(() => {
  stopAutoScroll()
  document.removeEventListener('mousemove', onDocMouseMove)
  document.removeEventListener('mouseup', onDocMouseUp)
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
})

// ---------------------------------------------------------------------------
// Expose for parent ref access
// ---------------------------------------------------------------------------

defineExpose({
  selectedIds,
  clearSelection: () => { selectedIds.value = new Set() },
})
</script>

<style scoped>
.ag {
  display: flex;
  width: 100%;
  height: 100%;
  min-height: 0;
  outline: none;
}

/* Label panel */
.ag-label-panel {
  display: flex;
  flex-direction: column;
  width: 170px;
  min-width: 170px;
  border-right: 1px solid var(--cv-border, rgba(255,255,255,0.12));
  background: var(--cv-card-bg, #1e1e2e);
}

.ag-label-search {
  margin: 8px;
  padding: 6px 8px;
  border: 1px solid var(--cv-border, rgba(255,255,255,0.12));
  border-radius: 4px;
  background: transparent;
  color: var(--cv-text, #fff);
  font-size: 12px;
  outline: none;
}

.ag-label-search::placeholder {
  color: var(--cv-text-disabled, rgba(255,255,255,0.3));
}

.ag-label-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 4px;
}

.ag-label-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  user-select: none;
  font-size: 12px;
  color: var(--cv-text, #fff);
}

.ag-label-item:hover {
  background: var(--cv-hover, rgba(255,255,255,0.08));
}

.ag-label-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.ag-label-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ag-label-shortcut {
  font-size: 10px;
  color: var(--cv-text-disabled, rgba(255,255,255,0.3));
  flex-shrink: 0;
}

.ag-label-add {
  margin: 4px 8px 8px;
  padding: 6px;
  border: 1px dashed var(--cv-border, rgba(255,255,255,0.12));
  border-radius: 4px;
  background: transparent;
  color: var(--cv-text-secondary, rgba(255,255,255,0.5));
  cursor: pointer;
  font-size: 12px;
}

.ag-label-add:hover {
  border-color: var(--cv-primary, #4098fc);
  color: var(--cv-primary, #4098fc);
}

/* Grid area */
.ag-grid-area {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.ag-scroll-container {
  flex: 1;
  overflow-y: auto;
  position: relative;
  padding: 8px;
}

.ag-card-row {
  display: flex;
  gap: 8px;
  flex-wrap: nowrap;
}

.ag-card {
  flex-shrink: 0;
  border: 2px solid transparent;
  border-radius: 6px;
  background: var(--cv-card-bg, #1e1e2e);
  cursor: pointer;
  overflow: hidden;
  transition: border-color 0.1s;
}

.ag-card:hover {
  border-color: var(--cv-border, rgba(255,255,255,0.2));
}

.ag-card--selected {
  border-color: var(--cv-primary, #4098fc) !important;
  box-shadow: 0 0 0 1px var(--cv-primary, #4098fc);
}

.ag-card-images {
  display: flex;
  overflow: hidden;
  background: #111;
}

.ag-card-img {
  width: 100%;
  object-fit: cover;
  flex-shrink: 0;
}

.ag-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 6px;
  min-height: 24px;
}

.ag-badge {
  display: inline-block;
  color: white;
  border-radius: 3px;
  padding: 1px 5px;
  font-size: 10px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.ag-badge--empty {
  background: transparent;
  color: var(--cv-text-disabled, rgba(255,255,255,0.3));
}

.ag-confidence {
  font-size: 10px;
  color: var(--cv-text-secondary, rgba(255,255,255,0.5));
  flex-shrink: 0;
}

/* Rubber band */
.ag-rubber-band {
  position: absolute;
  border: 2px dashed var(--cv-primary, #4098fc);
  background: color-mix(in srgb, var(--cv-primary, #4098fc) 15%, transparent);
  pointer-events: none;
  z-index: 10;
}

/* Bottom bar */
.ag-bottom-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-top: 1px solid var(--cv-border, rgba(255,255,255,0.12));
  background: var(--cv-card-bg, #1e1e2e);
  flex-shrink: 0;
}

.ag-bar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ag-bar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ag-bar-count {
  font-size: 12px;
  color: var(--cv-text-secondary, rgba(255,255,255,0.5));
}

.ag-submit-btn {
  padding: 6px 16px;
  border: none;
  border-radius: 4px;
  background: var(--cv-primary, #4098fc);
  color: white;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.ag-submit-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.ag-submit-btn:not(:disabled):hover {
  background: var(--cv-primary-hover, #3080e0);
}

/* Loading */
.ag-loading {
  padding: 12px;
  text-align: center;
  font-size: 12px;
  color: var(--cv-text-secondary, rgba(255,255,255,0.5));
}
</style>
