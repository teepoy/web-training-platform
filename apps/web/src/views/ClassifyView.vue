<template>
  <div class="classify-view" :style="themeStyleVars">
    <!-- Header bar -->
    <div class="classify-header">
      <n-button text @click="router.push(`/datasets/${datasetId}`)">
        <template #icon>
          <span>&#8592;</span>
        </template>
        Back
      </n-button>
      <n-divider vertical />
      <n-text tag="h2" style="margin: 0; font-size: 18px; font-weight: 600">
        {{ datasetQuery.data.value?.name ?? datasetId }}
      </n-text>
    </div>

    <!-- Toolbar row -->
    <div class="classify-toolbar">
      <div style="display: flex; align-items: center; gap: 12px; flex: 1; flex-wrap: wrap">
        <n-text depth="3" style="white-space: nowrap">Image size</n-text>
        <n-slider
          v-model:value="thumbSize"
          :min="64"
          :max="256"
          :step="8"
          style="width: 200px"
        />
        <n-text depth="3" style="white-space: nowrap">{{ thumbSize }}px</n-text>
        <n-select
          v-model:value="labelFilter"
          :options="filterOptions"
          placeholder="Filter by label"
          size="small"
          clearable
          style="width: 180px"
        />
        <n-select
          v-model:value="orderBy"
          :options="orderOptions"
          size="small"
          style="width: 150px"
        />
      </div>

      <n-text depth="3">
        {{ allSamples.length }} of {{ totalCount }} samples loaded
      </n-text>
    </div>

    <!-- Selection controls toolbar -->
    <div class="classify-toolbar" style="gap: 8px">
      <n-button size="small" @click="selectAll">Select All</n-button>
      <n-button size="small" @click="deselectAll">Deselect All</n-button>
      <n-text depth="3">{{ selectedIds.size }} of {{ allSamples.length }} selected</n-text>

      <!-- Keyboard shortcut legend -->
      <n-text
        v-if="labelSpace.length > 0"
        depth="3"
        style="margin-left: auto; font-size: 11px"
      >
        Keys: {{ labelSpace.map((l, i) => `${i + 1}=${l}`).join(', ') }}
      </n-text>
    </div>

    <!-- Bulk label toolbar -->
    <div class="classify-toolbar" style="gap: 8px">
      <n-select
        v-model:value="bulkLabel"
        :options="labelOptions"
        placeholder="Select label"
        size="small"
        style="width: 160px"
        clearable
      />
      <n-button
        size="small"
        @click="showAddLabelModal = true"
        title="Add a new label to this dataset"
      >
        + Add Label
      </n-button>
      <n-button
        size="small"
        :disabled="!bulkLabel || selectedIds.size === 0"
        @click="applyBulkLabel"
      >
        Apply to {{ selectedIds.size }} selected
      </n-button>
      <n-button
        type="primary"
        size="small"
        :loading="bulkAnnotateMutation.isPending.value"
        :disabled="draftCount === 0"
        @click="submitAnnotations"
      >
        Submit {{ draftCount }} Annotations
      </n-button>
    </div>

    <!-- Add Label Modal -->
    <n-modal v-model:show="showAddLabelModal" preset="dialog" title="Add New Label">
      <n-input
        v-model:value="newLabelName"
        placeholder="Enter label name"
        @keyup.enter="addNewLabel"
      />
      <template #action>
        <n-button @click="showAddLabelModal = false">Cancel</n-button>
        <n-button
          type="primary"
          :loading="addLabelMutation.isPending.value"
          :disabled="!newLabelName.trim()"
          @click="addNewLabel"
        >
          Add
        </n-button>
      </template>
    </n-modal>

    <!-- Table container -->
    <DnDProvider>
      <div
        ref="tableContainerRef"
        class="table-container"
        @mousedown="onTableMouseDown"
      >
        <!-- Sticky header -->
        <div class="table-head" :style="{ width: totalTableWidth + 'px', minWidth: '100%' }">
          <table :style="{ width: totalTableWidth + 'px', tableLayout: 'fixed', borderCollapse: 'collapse' }">
            <thead>
              <tr>
                <th
                  v-for="(header, hIdx) in table.getFlatHeaders()"
                  :key="header.id"
                  :style="{
                    width: (header.getSize() + (hIdx === table.getFlatHeaders().length - 1 ? lastColExtraWidth : 0)) + 'px',
                    minWidth: (header.getSize() + (hIdx === table.getFlatHeaders().length - 1 ? lastColExtraWidth : 0)) + 'px',
                    position: 'relative',
                  }"
                  class="table-th"
                  :class="{ 'th-dragging': draggingHeaderId === header.id }"
                  :draggable="header.id !== 'checkbox'"
                  @dragstart="onHeaderDragStart(header.id)"
                  @dragover="onHeaderDragOver($event, header.id)"
                  @drop.prevent="onHeaderDrop(header.id)"
                  @dragend="onHeaderDragEnd"
                >
                  <div class="th-content">
                    <FlexRender
                      :render="header.column.columnDef.header"
                      :props="header.getContext()"
                    />
                  </div>
                  <!-- Resize handle (only on resizable columns) -->
                  <div
                    v-if="header.column.getCanResize()"
                    class="resize-handle"
                    draggable="false"
                    @mousedown.stop.prevent="header.getResizeHandler()($event)"
                    @dragstart.stop.prevent
                  />
                </th>
              </tr>
            </thead>
          </table>
        </div>

        <!-- Virtual scroll body -->
        <div :style="{ width: totalTableWidth + 'px', minWidth: '100%' }">
          <div
            class="virtual-scroll-body"
            :style="{ height: virtualizer.getTotalSize() + 'px', position: 'relative' }"
          >
            <div
              v-for="virtualRow in virtualizer.getVirtualItems()"
              :key="virtualRow.index"
              :style="{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                height: virtualRow.size + 'px',
                transform: `translateY(${virtualRow.start}px)`,
              }"
            >
              <table
                v-if="allSamples[virtualRow.index]"
                :style="{ tableLayout: 'fixed', width: totalTableWidth + 'px', borderCollapse: 'collapse' }"
              >
                <tbody>
                  <tr
                    :class="['table-row', selectedIds.has(allSamples[virtualRow.index].id) && 'table-row--selected']"
                    @click="onRowClick(virtualRow.index, $event)"
                  >
                    <td
                      v-for="header in table.getFlatHeaders()"
                      :key="header.id"
                      :style="cellStyle(header)"
                      :class="cellClass(header.id)"
                    >
                      <!-- Checkbox -->
                      <template v-if="header.id === 'checkbox'">
                        <div
                          :class="['cell-checkbox', selectedIds.has(allSamples[virtualRow.index].id) && 'cell-checkbox--checked']"
                          @click.stop="toggleSelect(allSamples[virtualRow.index].id)"
                        />
                      </template>

                      <!-- Images -->
                      <template v-else-if="header.id === 'images'">
                        <div class="image-cell-inner" :style="{ height: imageColWidth + 'px' }">
                          <img
                            v-for="(src, imgIdx) in resolveImageUris(allSamples[virtualRow.index].image_uris ?? [])"
                            :key="imgIdx"
                            :src="src"
                            loading="lazy"
                            alt=""
                            :style="{ width: imageColWidth + 'px', height: imageColWidth + 'px', objectFit: 'cover', borderRadius: '4px', flexShrink: 0 }"
                          />
                        </div>
                      </template>

                      <!-- ID -->
                      <template v-else-if="header.id === 'id'">
                        <span class="cell-text-truncate" :title="allSamples[virtualRow.index].id">{{ allSamples[virtualRow.index].id }}</span>
                      </template>

                      <!-- Annotation -->
                      <template v-else-if="header.id === 'annotation'">
                        <span
                          v-if="allSamples[virtualRow.index].latest_annotation?.label"
                          class="label-badge"
                          :style="{ background: labelColor(allSamples[virtualRow.index].latest_annotation!.label, labelSpace) }"
                        >{{ allSamples[virtualRow.index].latest_annotation!.label }}</span>
                        <span v-else class="cell-empty">&mdash;</span>
                      </template>

                      <!-- Draft Label -->
                      <template v-else-if="header.id === 'draft'">
                        <span
                          v-if="labelDraft[allSamples[virtualRow.index].id]"
                          class="label-badge label-badge--draft"
                        >{{ labelDraft[allSamples[virtualRow.index].id] }}</span>
                      </template>

                      <!-- Metadata -->
                      <template v-else-if="header.id === 'metadata'">
                        <span class="cell-text-truncate" :title="JSON.stringify(allSamples[virtualRow.index].metadata)">
                          {{ JSON.stringify(allSamples[virtualRow.index].metadata) }}
                        </span>
                      </template>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- Rubber band rect overlay -->
        <div
          v-if="isDragging && dragStart && dragCurrent"
          class="rubber-band-rect"
          :style="rubberBandStyle"
        />

        <!-- Loading indicator -->
        <div v-if="isLoadingMore" class="loading-indicator">
          Loading more samples&hellip;
        </div>
      </div>
    </DnDProvider>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQuery, useMutation } from '@tanstack/vue-query'
import {
  useVueTable,
  getCoreRowModel,
  createColumnHelper,
  FlexRender,
  type ColumnSizingState,
  type ColumnSizingInfoState,
} from '@tanstack/vue-table'
import { useVirtualizer } from '@tanstack/vue-virtual'
import { DnDProvider } from '@vue-dnd-kit/core'
import { NButton, NText, NSlider, NDivider, NSelect, NModal, NInput, useMessage, useDialog, useThemeVars } from 'naive-ui'
import { listSamplesWithLabels, api, bulkCreateAnnotations, syncAnnotationsToLs } from '../api'
import type { SampleWithLabels, BulkAnnotationRequest, BulkAnnotationResponse, SyncResult, Dataset } from '../types'
import { resolveImageUris } from '../utils/imageAdapters'

const route = useRoute()
const router = useRouter()
const datasetId = route.params.id as string
const message = useMessage()
const dialog = useDialog()
const themeVars = useThemeVars()

const themeStyleVars = computed(() => ({
  '--cv-bg': themeVars.value.bodyColor,
  '--cv-card-bg': themeVars.value.cardColor,
  '--cv-text': themeVars.value.textColor1,
  '--cv-text-secondary': themeVars.value.textColor3,
  '--cv-text-disabled': themeVars.value.textColorDisabled,
  '--cv-border': themeVars.value.borderColor,
  '--cv-divider': themeVars.value.dividerColor,
  '--cv-hover': themeVars.value.hoverColor,
  '--cv-primary': themeVars.value.primaryColor,
  '--cv-primary-hover': themeVars.value.primaryColorHover,
}))

// Dataset query (for header title)
const datasetQuery = useQuery({
  queryKey: ['dataset', datasetId],
  queryFn: () => api.getDataset(datasetId),
  retry: false,
})

// Color palette — 10 distinguishable colors
const LABEL_COLORS = [
  '#4CAF50', '#2196F3', '#FF9800', '#E91E63', '#9C27B0',
  '#00BCD4', '#FF5722', '#795548', '#607D8B', '#CDDC39',
]

function labelColor(label: string, space: string[]): string {
  const idx = space.indexOf(label)
  if (idx === -1) return '#9E9E9E'
  return LABEL_COLORS[idx % LABEL_COLORS.length]
}

// Get label_space from the dataset query
const labelSpace = computed<string[]>(
  () => datasetQuery.data.value?.task_spec?.label_space ?? []
)

// Badge label for display (used indirectly via effectiveBadgeLabel)
function badgeLabel(sample: SampleWithLabels): string | null {
  return sample.latest_annotation?.label ?? null
}

// Effective badge label: draft overrides annotation
function effectiveBadgeLabel(sample: SampleWithLabels): string | null {
  if (labelDraft.value[sample.id]) return labelDraft.value[sample.id]
  return badgeLabel(sample)
}
// Kept for potential future use in template badge overlays
void effectiveBadgeLabel

// Thumb size controls the image column width
const thumbSize = ref(128)
const imageColWidth = computed(() => thumbSize.value)

// Filter / sort state
const labelFilter = ref<string | null>(null)
const orderBy = ref<string>('id')

// Infinite loading state
const allSamples = ref<SampleWithLabels[]>([])
const totalCount = ref(0)
const PAGE_SIZE = 100
const isLoadingMore = ref(false)
const hasMore = computed(() => allSamples.value.length < totalCount.value)

// Selection state
const selectedIds = ref<Set<string>>(new Set())

// Label draft (pending, not yet submitted)
const labelDraft = ref<Record<string, string>>({})

// Bulk label UI
const bulkLabel = ref<string | null>(null)

const filterOptions = computed(() => ([
  { label: 'All', value: null as string | null },
  { label: 'Unlabeled', value: '__unlabeled__' as string | null },
  ...labelSpace.value.map((l) => ({ label: l, value: l as string | null })),
] as any))

const labelOptions = computed(() =>
  labelSpace.value.map((l) => ({ label: l, value: l }))
)

const orderOptions = [
  { label: 'Default (id)', value: 'id' },
  { label: 'By Label', value: 'label' },
  { label: 'Newest First', value: 'created_at' },
] as any

const draftCount = computed(() =>
  Object.keys(labelDraft.value).filter((k) => labelDraft.value[k]).length
)

// ─── Fetching logic ────────────────────────────────────────────────────────────

async function loadPage(offset: number) {
  isLoadingMore.value = true
  try {
    const result = await listSamplesWithLabels(
      datasetId,
      offset,
      PAGE_SIZE,
      labelFilter.value ?? undefined,
      orderBy.value
    )
    totalCount.value = result.total
    allSamples.value = [...allSamples.value, ...result.items]
  } finally {
    isLoadingMore.value = false
  }
}

function resetAndFetch() {
  allSamples.value = []
  totalCount.value = 0
  loadPage(0)
}

// Initial load
onMounted(() => {
  resetAndFetch()
  document.addEventListener('keydown', onKeyDown)
  // Set up ResizeObserver for container width tracking
  if (tableContainerRef.value) {
    containerWidth.value = tableContainerRef.value.clientWidth
    resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        containerWidth.value = entry.contentRect.width
      }
    })
    resizeObserver.observe(tableContainerRef.value)
  }
})

// Reset when filters change
watch([labelFilter, orderBy], () => {
  resetAndFetch()
})

// ─── TanStack Table setup ──────────────────────────────────────────────────────

const columnHelper = createColumnHelper<SampleWithLabels>()

// Column sizing state
const columnSizing = ref<ColumnSizingState>({})
const columnSizingInfo = ref<ColumnSizingInfoState>({
  startOffset: null,
  startSize: null,
  deltaOffset: null,
  deltaPercentage: null,
  isResizingColumn: false,
  columnSizingStart: [],
})

// Column width defaults
const colDefaults: Record<string, number> = {
  checkbox: 40,
  images: 128,
  id: 120,
  annotation: 120,
  draft: 100,
  metadata: 200,
}

// Column order state
const columnOrder = ref<string[]>(['checkbox', 'images', 'id', 'annotation', 'draft', 'metadata'])

// Define columns using createColumnHelper
const columns = [
  columnHelper.display({
    id: 'checkbox',
    size: 40,
    minSize: 40,
    maxSize: 40,
    enableResizing: false,
    header: () => 'Select',
    cell: () => null,
  }),
  columnHelper.display({
    id: 'images',
    size: imageColWidth.value,
    minSize: 64,
    maxSize: 512,
    enableResizing: true,
    header: () => 'Image(s)',
    cell: () => null,
  }),
  columnHelper.accessor('id', {
    id: 'id',
    size: 120,
    minSize: 60,
    enableResizing: true,
    header: () => 'ID',
    cell: () => null,
  }),
  columnHelper.display({
    id: 'annotation',
    size: 120,
    minSize: 60,
    enableResizing: true,
    header: () => 'Annotation',
    cell: () => null,
  }),
  columnHelper.display({
    id: 'draft',
    size: 100,
    minSize: 60,
    enableResizing: true,
    header: () => 'Draft Label',
    cell: () => null,
  }),
  columnHelper.display({
    id: 'metadata',
    size: 200,
    minSize: 80,
    enableResizing: true,
    header: () => 'Metadata',
    cell: () => null,
  }),
]

const table = useVueTable({
  get data() { return allSamples.value },
  columns,
  state: {
    get columnSizing() { return columnSizing.value },
    get columnSizingInfo() { return columnSizingInfo.value },
    get columnOrder() { return columnOrder.value },
  },
  enableColumnResizing: true,
  columnResizeMode: 'onChange',
  onColumnSizingChange: (updater) => {
    columnSizing.value = typeof updater === 'function' ? updater(columnSizing.value) : updater
    nextTick(() => { virtualizer.value.measure() })
  },
  onColumnSizingInfoChange: (updater) => {
    columnSizingInfo.value = typeof updater === 'function' ? updater(columnSizingInfo.value) : updater
  },
  onColumnOrderChange: (updater) => {
    columnOrder.value = typeof updater === 'function' ? updater(columnOrder.value) : updater
  },
  getCoreRowModel: getCoreRowModel(),
})

// Helpers to get column widths from TanStack state
function getColWidth(colId: string): number {
  const col = table.getColumn(colId)
  if (col) return col.getSize()
  return colDefaults[colId] ?? 120
}

// Total table width (at least container width so last column can fill space)
const totalTableWidth = computed(() => {
  const naturalWidth = table.getFlatHeaders().reduce((sum, h) => sum + h.getSize(), 0)
  return Math.max(naturalWidth, containerWidth.value)
})

// Compute extra width to assign to the last column so it fills remaining space
const lastColExtraWidth = computed(() => {
  const headers = table.getFlatHeaders()
  if (headers.length === 0) return 0
  const naturalWidth = headers.reduce((sum, h) => sum + h.getSize(), 0)
  const extra = containerWidth.value - naturalWidth
  return extra > 0 ? extra : 0
})

// Per-cell style and class helpers (driven by header order for column reorder support)
function cellStyle(header: { id: string; getSize: () => number }) {
  const headers = table.getFlatHeaders()
  const isLast = headers.length > 0 && headers[headers.length - 1].id === header.id
  const w = header.getSize() + (isLast ? lastColExtraWidth.value : 0)
  const base: Record<string, string> = { width: w + 'px', minWidth: w + 'px' }
  if (header.id === 'images') base.height = imageColWidth.value + 'px'
  return base
}

function cellClass(colId: string): string[] {
  const cls = ['table-td']
  if (colId === 'checkbox') cls.push('td-checkbox')
  else if (colId === 'images') cls.push('td-image')
  else if (colId === 'id' || colId === 'metadata') cls.push('td-text')
  return cls
}

// Watch thumbSize to update the images column size
watch(thumbSize, (newSize) => {
  columnSizing.value = { ...columnSizing.value, images: newSize }
  nextTick(() => { virtualizer.value.measure() })
})

// ─── Virtualizer setup ─────────────────────────────────────────────────────────

const tableContainerRef = ref<HTMLElement | null>(null)
const containerWidth = ref(0)

// Track container width with ResizeObserver for last-column-fill
let resizeObserver: ResizeObserver | null = null

const virtualizer = useVirtualizer({
  get count() { return allSamples.value.length },
  getScrollElement: () => tableContainerRef.value,
  estimateSize: () => imageColWidth.value,
  overscan: 5,
})

// Watch virtualizer items to trigger next-page load
watch(
  () => virtualizer.value.getVirtualItems(),
  (items) => {
    if (!items.length) return
    const lastItem = items[items.length - 1]
    if (lastItem.index >= allSamples.value.length - 10 && hasMore.value && !isLoadingMore.value) {
      loadPage(allSamples.value.length)
    }
  }
)

// ─── Column drag-to-reorder ────────────────────────────────────────────────────

const draggingHeaderId = ref<string | null>(null)

let dragSourceColId: string | null = null

function onHeaderDragStart(colId: string) {
  dragSourceColId = colId
  draggingHeaderId.value = colId
}

function onHeaderDragOver(e: DragEvent, _colId: string) {
  e.preventDefault()
}

function onHeaderDrop(colId: string) {
  if (!dragSourceColId || dragSourceColId === colId) {
    dragSourceColId = null
    draggingHeaderId.value = null
    return
  }

  const order = [...columnOrder.value]
  const fromIdx = order.indexOf(dragSourceColId)
  const toIdx = order.indexOf(colId)
  if (fromIdx !== -1 && toIdx !== -1) {
    order.splice(fromIdx, 1)
    order.splice(toIdx, 0, dragSourceColId)
    table.setColumnOrder(order)
  }

  dragSourceColId = null
  draggingHeaderId.value = null
}

function onHeaderDragEnd() {
  draggingHeaderId.value = null
  dragSourceColId = null
}

// ─── Row selection ─────────────────────────────────────────────────────────────

function toggleSelect(id: string) {
  const next = new Set(selectedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedIds.value = next
}

function onRowClick(rowIndex: number, e: MouseEvent) {
  if (wasDragging) return
  const sample = allSamples.value[rowIndex]
  if (!sample) return
  if (e.ctrlKey || e.metaKey) {
    toggleSelect(sample.id)
  } else {
    selectedIds.value = new Set([sample.id])
  }
}

function selectAll() {
  selectedIds.value = new Set(allSamples.value.map((s) => s.id))
}

function deselectAll() {
  selectedIds.value = new Set()
}

// ─── Rubber-band drag-select ───────────────────────────────────────────────────

const isDragging = ref(false)
const dragStart = ref<{ x: number; y: number } | null>(null)
const dragCurrent = ref<{ x: number; y: number } | null>(null)
const DRAG_THRESHOLD = 5
let wasDragging = false
let cachedContainerRect: DOMRect | null = null
let dragCtrlHeld = false

const rubberBandStyle = computed(() => {
  if (!dragStart.value || !dragCurrent.value || !cachedContainerRect) return {}
  const rect = cachedContainerRect
  const x1 = Math.min(dragStart.value.x, dragCurrent.value.x)
  const y1 = Math.min(dragStart.value.y, dragCurrent.value.y)
  const x2 = Math.max(dragStart.value.x, dragCurrent.value.x)
  const y2 = Math.max(dragStart.value.y, dragCurrent.value.y)
  return {
    left: (x1 - rect.left) + 'px',
    top: (y1 - rect.top) + 'px',
    width: (x2 - x1) + 'px',
    height: (y2 - y1) + 'px',
  }
})

function onTableMouseDown(e: MouseEvent) {
  if (e.button !== 0) return
  // Don't start rubber-band if clicking on a header (allows HTML5 drag for column reorder)
  if ((e.target as HTMLElement).closest('thead')) return
  e.preventDefault()
  cachedContainerRect = tableContainerRef.value?.getBoundingClientRect() ?? null
  dragStart.value = { x: e.clientX, y: e.clientY }
  dragCurrent.value = { x: e.clientX, y: e.clientY }
  dragCtrlHeld = e.ctrlKey || e.metaKey
  document.addEventListener('mousemove', onDocMouseMove)
  document.addEventListener('mouseup', onDocMouseUp)
}

function onDocMouseMove(e: MouseEvent) {
  if (!dragStart.value) return
  dragCurrent.value = { x: e.clientX, y: e.clientY }
  const dx = dragCurrent.value.x - dragStart.value.x
  const dy = dragCurrent.value.y - dragStart.value.y
  if (!isDragging.value && Math.sqrt(dx * dx + dy * dy) >= DRAG_THRESHOLD) {
    isDragging.value = true
  }
}

function onDocMouseUp(_e: MouseEvent) {
  document.removeEventListener('mousemove', onDocMouseMove)
  document.removeEventListener('mouseup', onDocMouseUp)

  if (isDragging.value && dragStart.value && dragCurrent.value && cachedContainerRect && tableContainerRef.value) {
    const scrollTop = tableContainerRef.value.scrollTop
    const containerTop = cachedContainerRect.top

    // Rubber-band bounds in viewport space → content space
    const selTop = Math.min(dragStart.value.y, dragCurrent.value.y)
    const selBottom = Math.max(dragStart.value.y, dragCurrent.value.y)
    const contentSelTop = selTop - containerTop + scrollTop
    const contentSelBottom = selBottom - containerTop + scrollTop

    // Find virtual items whose Y range overlaps selection
    const virtualItems = virtualizer.value.getVirtualItems()
    const intersecting: string[] = []
    for (const item of virtualItems) {
      const itemTop = item.start
      const itemBottom = item.start + item.size
      if (itemBottom >= contentSelTop && itemTop <= contentSelBottom) {
        const sample = allSamples.value[item.index]
        if (sample) intersecting.push(sample.id)
      }
    }

    if (dragCtrlHeld) {
      const next = new Set(selectedIds.value)
      intersecting.forEach((id) => next.add(id))
      selectedIds.value = next
    } else {
      selectedIds.value = new Set(intersecting)
    }

    wasDragging = true
    setTimeout(() => { wasDragging = false }, 0)
  }

  isDragging.value = false
  dragStart.value = null
  dragCurrent.value = null
  cachedContainerRect = null
}

// ─── Label operations ──────────────────────────────────────────────────────────

function applyLabel(label: string, ids: Set<string>) {
  if (ids.size === 0) return
  const draft = { ...labelDraft.value }
  ids.forEach((id) => { draft[id] = label })
  labelDraft.value = draft
}

function applyBulkLabel() {
  if (!bulkLabel.value) return
  applyLabel(bulkLabel.value, selectedIds.value)
}

// Keyboard shortcuts: 1-9 assign labelSpace[N-1] to selected samples
function onKeyDown(e: KeyboardEvent) {
  const el = document.activeElement
  if (
    el instanceof HTMLInputElement ||
    el instanceof HTMLSelectElement ||
    el instanceof HTMLTextAreaElement ||
    (el instanceof HTMLElement && el.isContentEditable)
  )
    return

  const num = parseInt(e.key, 10)
  if (isNaN(num) || num < 1 || num > 9) return
  const label = labelSpace.value[num - 1]
  if (!label) return
  if (selectedIds.value.size === 0) return
  applyLabel(label, selectedIds.value)
}

// ─── Mutations ─────────────────────────────────────────────────────────────────

const syncToLsMutation = useMutation({
  mutationFn: () => syncAnnotationsToLs(datasetId),
  onSuccess: (data: SyncResult) => {
    message.success(`Synced ${data.synced_count} annotations to Label Studio`)
  },
  onError: (err: Error) => {
    message.error(err.message ?? 'Failed to sync to Label Studio')
  },
})

const bulkAnnotateMutation = useMutation({
  mutationFn: (body: BulkAnnotationRequest) => bulkCreateAnnotations(datasetId, body),
  onSuccess: (data: BulkAnnotationResponse) => {
    message.success(`Created ${data.created} annotations`)
    if (datasetQuery.data.value?.ls_project_id) {
      syncToLsMutation.mutate()
    }
    labelDraft.value = {}
    selectedIds.value = new Set()
    resetAndFetch()
  },
  onError: (err: Error) => {
    message.error(err.message ?? 'Failed to create annotations')
  },
})

function submitAnnotations() {
  const entries = Object.entries(labelDraft.value).filter(([, label]) => label)
  if (entries.length === 0) {
    message.warning('No annotations to submit')
    return
  }
  dialog.warning({
    title: 'Submit annotations?',
    content: `This will create ${entries.length} annotation(s). Continue?`,
    positiveText: 'Submit',
    negativeText: 'Cancel',
    onPositiveClick: () => {
      bulkAnnotateMutation.mutate({
        annotations: entries.map(([sample_id, label]) => ({
          sample_id,
          label,
          annotator: 'platform-user',
        })),
      })
    },
  })
}

// ─── Add Label ─────────────────────────────────────────────────────────────────

const showAddLabelModal = ref(false)
const newLabelName = ref('')

const addLabelMutation = useMutation({
  mutationFn: (newLabel: string) => {
    const currentLabels = labelSpace.value
    if (currentLabels.includes(newLabel)) {
      throw new Error(`Label "${newLabel}" already exists`)
    }
    return api.updateLabelSpace(datasetId, [...currentLabels, newLabel])
  },
  onSuccess: (data: Dataset) => {
    message.success(`Added label "${newLabelName.value}"`)
    showAddLabelModal.value = false
    newLabelName.value = ''
    // Refetch dataset to get updated label space
    datasetQuery.refetch()
  },
  onError: (err: Error) => {
    message.error(err.message ?? 'Failed to add label')
  },
})

function addNewLabel() {
  const trimmed = newLabelName.value.trim()
  if (!trimmed) return
  addLabelMutation.mutate(trimmed)
}

onUnmounted(() => {
  document.removeEventListener('keydown', onKeyDown)
  document.removeEventListener('mousemove', onDocMouseMove)
  document.removeEventListener('mouseup', onDocMouseUp)
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
})
</script>

<style scoped>
.classify-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  padding: 12px;
  box-sizing: border-box;
  color: var(--cv-text);
}

.classify-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-shrink: 0;
}

.classify-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
  flex-shrink: 0;
}

.table-container {
  overflow: auto;
  flex: 1;
  position: relative;
  border: 1px solid var(--cv-border);
  border-radius: 6px;
  background: var(--cv-card-bg);
}

.table-head {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--cv-card-bg);
}

.table-th {
  padding: 8px;
  border-bottom: 2px solid var(--cv-border);
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  user-select: none;
  text-align: left;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  background: var(--cv-card-bg);
  color: var(--cv-text);
}

.table-th.th-dragging {
  opacity: 0.5;
}

.th-content {
  padding-right: 4px;
}

.resize-handle {
  position: absolute;
  right: -3px;
  top: 0;
  height: 100%;
  width: 7px;
  cursor: col-resize;
  background: transparent;
  z-index: 3;
}

.resize-handle:hover {
  background: var(--cv-primary);
}

.virtual-scroll-body {
  /* height is set inline via virtualizer.getTotalSize() */
}

.table-row {
  cursor: pointer;
}

.table-row:hover {
  background: var(--cv-hover);
}

.table-row--selected {
  background: color-mix(in srgb, var(--cv-primary) 12%, transparent) !important;
  outline: 1px solid var(--cv-primary);
}

.table-td {
  padding: 4px 8px;
  border-bottom: 1px solid var(--cv-divider);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  vertical-align: middle;
  color: var(--cv-text);
}

.td-checkbox {
  text-align: center;
  padding: 0;
}

.td-image {
  padding: 2px 4px;
}

.image-cell-inner {
  display: flex;
  flex-direction: row;
  gap: 2px;
  overflow: hidden;
}

.td-text {
  font-size: 12px;
  color: var(--cv-text-secondary);
}

.cell-text-truncate {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}

.cell-empty {
  color: var(--cv-text-disabled);
  font-size: 12px;
}

.label-badge {
  display: inline-block;
  color: white;
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
}

.label-badge--draft {
  background: var(--cv-primary);
  color: white;
}

.badge-score {
  font-size: 10px;
  opacity: 0.85;
}

.cell-checkbox {
  width: 18px;
  height: 18px;
  border: 2px solid var(--cv-border);
  border-radius: 4px;
  background: var(--cv-card-bg);
  cursor: pointer;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.1s, border-color 0.1s;
}

.cell-checkbox--checked {
  background: var(--cv-primary);
  border-color: var(--cv-primary);
}

.cell-checkbox--checked::after {
  content: '✓';
  color: white;
  font-size: 12px;
  line-height: 1;
}

.rubber-band-rect {
  position: absolute;
  border: 2px dashed var(--cv-primary);
  background: color-mix(in srgb, var(--cv-primary) 15%, transparent);
  pointer-events: none;
  z-index: 10;
}

.loading-indicator {
  position: sticky;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 8px 16px;
  background: color-mix(in srgb, var(--cv-card-bg) 90%, transparent);
  font-size: 12px;
  color: var(--cv-text-secondary);
  text-align: center;
  border-top: 1px solid var(--cv-border);
}
</style>
