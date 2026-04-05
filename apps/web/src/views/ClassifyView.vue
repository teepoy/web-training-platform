<template>
  <div class="classify-view">
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
        <n-text depth="3" style="white-space: nowrap">Thumbnail size</n-text>
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
        <n-radio-group v-model:value="viewMode" size="small">
          <n-radio-button value="annotations">Annotations</n-radio-button>
          <n-radio-button value="predictions">Predictions</n-radio-button>
        </n-radio-group>
      </div>

      <n-text depth="3">
        {{ pageOffset + 1 }}–{{ Math.min(pageOffset + pageSize, totalCount) }} of {{ totalCount }} samples
      </n-text>
    </div>

    <!-- Selection controls toolbar -->
    <div class="classify-toolbar" style="gap: 8px">
      <n-button size="small" @click="selectAll">Select All</n-button>
      <n-button size="small" @click="deselectAll">Deselect All</n-button>
      <n-text depth="3">{{ selectedIds.size }} of {{ pageSamples.length }} selected</n-text>

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

    <!-- CSS grid -->
    <div
      :key="gridLayoutVersion"
      ref="gridContainer"
      :class="['classify-grid', isDragging && 'classify-grid--dragging']"
      :style="{ '--cell-size': thumbSize + 'px' }"
      @mousedown.prevent="onGridMouseDown"
    >
      <div
        v-for="sample in pageSamples"
        :key="sample.id"
        :data-sample-id="sample.id"
        :class="['grid-cell', selectedIds.has(sample.id) && 'grid-cell--selected', isDragging && 'grid-cell--no-click']"
        :style="labelDraft[sample.id] ? { borderColor: '#18a058' } : {}"
        @click="onCellClick(sample.id)"
      >
        <!-- Checkbox overlay top-left -->
        <div
          class="cell-checkbox"
          :class="{ 'cell-checkbox--checked': selectedIds.has(sample.id) }"
          @click.stop="toggleSelect(sample.id)"
        />

        <img
          :src="resolveImageUris(sample.image_uris ?? [])[0]"
          loading="lazy"
          alt=""
        />
        <span
          v-if="effectiveBadgeLabel(sample)"
          :style="{
            position: 'absolute',
            bottom: '4px',
            left: '4px',
            background: labelColor(effectiveBadgeLabel(sample)!, labelSpace),
            color: 'white',
            borderRadius: '4px',
            padding: '2px 6px',
            fontSize: '11px',
            pointerEvents: 'none',
          }"
        >{{ effectiveBadgeLabel(sample) }}</span>
      </div>
      <div
        v-if="isDragging && dragStart && dragCurrent"
        class="rubber-band-rect"
        :style="rubberBandStyle"
      />
    </div>

    <!-- Pagination -->
    <div style="margin-top: 12px; display: flex; justify-content: flex-end">
      <n-pagination
        v-model:page="currentPage"
        :page-size="pageSize"
        :item-count="totalCount"
        show-size-picker
        :page-sizes="pageSizes"
        @update:page-size="onPageSizeChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQuery, useMutation, keepPreviousData } from '@tanstack/vue-query'
import { NButton, NText, NSlider, NDivider, NSelect, NRadioGroup, NRadioButton, useMessage, useDialog } from 'naive-ui'
import { listSamplesWithLabels, api, bulkCreateAnnotations, syncAnnotationsToLs } from '../api'
import type { SampleWithLabels, BulkAnnotationRequest, BulkAnnotationResponse, SyncResult } from '../types'
import { resolveImageUris } from '../utils/imageAdapters'

const route = useRoute()
const router = useRouter()
const datasetId = route.params.id as string
const message = useMessage()
const dialog = useDialog()

// Dataset query (for header title)
const datasetQuery = useQuery({
  queryKey: ['dataset', datasetId],
  queryFn: () => api.getDataset(datasetId),
  retry: false,
})

// Mode toggle
const viewMode = ref<'annotations' | 'predictions'>('annotations')

// Color palette — 10 distinguishable colors
const LABEL_COLORS = [
  '#4CAF50', '#2196F3', '#FF9800', '#E91E63', '#9C27B0',
  '#00BCD4', '#FF5722', '#795548', '#607D8B', '#CDDC39',
]

function labelColor(label: string, space: string[]): string {
  const idx = space.indexOf(label)
  if (idx === -1) return '#9E9E9E' // gray fallback
  return LABEL_COLORS[idx % LABEL_COLORS.length]
}

// Get label_space from the dataset query
const labelSpace = computed<string[]>(
  () => datasetQuery.data.value?.task_spec?.label_space ?? []
)

// Current badge label for a sample (derived from viewMode)
function badgeLabel(sample: SampleWithLabels): string | null {
  if (viewMode.value === 'annotations') {
    return sample.latest_annotation?.label ?? null
  } else {
    return sample.latest_prediction?.predicted_label ?? null
  }
}

// Effective badge label: draft overrides annotation/prediction
function effectiveBadgeLabel(sample: SampleWithLabels): string | null {
  if (labelDraft.value[sample.id]) return labelDraft.value[sample.id]
  return badgeLabel(sample)
}

// Grid state
const thumbSize = ref(128)
const labelFilter = ref<string | null>(null)
const orderBy = ref<string>('id')
const gridLayoutVersion = ref(0)
const gridContainer = ref<HTMLElement | null>(null)
const pendingScrollTop = ref<number | null>(null)

// Rubber-band drag state
const isDragging = ref(false)
const dragStart = ref<{ x: number; y: number } | null>(null)
const dragCurrent = ref<{ x: number; y: number } | null>(null)
const DRAG_THRESHOLD = 5
let wasDragging = false
let cachedGridRect: DOMRect | null = null

// Pagination state
const currentPage = ref(1)
const pageSize = ref(50)
const pageSizes = [50, 100, 200]
const pageOffset = computed(() => (currentPage.value - 1) * pageSize.value)

// --- Selection state ---
const selectedIds = ref<Set<string>>(new Set())

// --- Label draft (pending, not yet submitted) ---
const labelDraft = ref<Record<string, string>>({})

// --- Bulk label UI ---
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

// Draft count — number of pending (non-empty) label drafts
const draftCount = computed(() =>
  Object.keys(labelDraft.value).filter((k) => labelDraft.value[k]).length
)

// Samples query (Vue Query with pagination)
const samplesQuery = useQuery({
  queryKey: computed(() => ['classify-samples', datasetId, currentPage.value, pageSize.value, labelFilter.value, orderBy.value]),
  queryFn: () => listSamplesWithLabels(datasetId, pageOffset.value, pageSize.value, labelFilter.value ?? undefined, orderBy.value),
  placeholderData: keepPreviousData,
})

const pageSamples = computed(() => samplesQuery.data.value?.items ?? [])
const totalCount = computed(() => samplesQuery.data.value?.total ?? 0)

function onPageSizeChange(newSize: number) {
  pageSize.value = newSize
  currentPage.value = 1
}

// Mutations
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
    currentPage.value = 1
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

watch([labelFilter, orderBy], () => {
  currentPage.value = 1
})

watch(thumbSize, () => {
  void refreshGridLayout()
})

async function refreshGridLayout() {
  pendingScrollTop.value = gridContainer.value?.scrollTop ?? null
  gridLayoutVersion.value += 1
  await nextTick()
  if (gridContainer.value && pendingScrollTop.value !== null) {
    gridContainer.value.scrollTop = pendingScrollTop.value
  }
}

const rubberBandStyle = computed(() => {
  if (!dragStart.value || !dragCurrent.value) return {}
  const x1 = Math.min(dragStart.value.x, dragCurrent.value.x)
  const y1 = Math.min(dragStart.value.y, dragCurrent.value.y)
  const x2 = Math.max(dragStart.value.x, dragCurrent.value.x)
  const y2 = Math.max(dragStart.value.y, dragCurrent.value.y)
  const rect = cachedGridRect
  if (!rect) return {}
  return {
    left: (x1 - rect.left) + 'px',
    top: (y1 - rect.top) + 'px',
    width: (x2 - x1) + 'px',
    height: (y2 - y1) + 'px',
  }
})

function onGridMouseDown(e: MouseEvent) {
  if (e.button !== 0) return
  cachedGridRect = gridContainer.value?.getBoundingClientRect() ?? null
  dragStart.value = { x: e.clientX, y: e.clientY }
  dragCurrent.value = { x: e.clientX, y: e.clientY }
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

  if (isDragging.value && dragStart.value && dragCurrent.value && cachedGridRect) {
    const selLeft = Math.min(dragStart.value.x, dragCurrent.value.x)
    const selTop = Math.min(dragStart.value.y, dragCurrent.value.y)
    const selRight = Math.max(dragStart.value.x, dragCurrent.value.x)
    const selBottom = Math.max(dragStart.value.y, dragCurrent.value.y)

    const cells = gridContainer.value?.querySelectorAll<HTMLElement>('.grid-cell[data-sample-id]') ?? []
    const intersecting: string[] = []
    cells.forEach((cell) => {
      const cr = cell.getBoundingClientRect()
      const overlaps = !(cr.right < selLeft || cr.left > selRight || cr.bottom < selTop || cr.top > selBottom)
      if (overlaps) {
        const id = cell.dataset.sampleId
        if (id) intersecting.push(id)
      }
    })
    selectedIds.value = new Set(intersecting)

    wasDragging = true
    setTimeout(() => { wasDragging = false }, 0)
  }

  isDragging.value = false
  dragStart.value = null
  dragCurrent.value = null
  cachedGridRect = null
}

function onCellClick(id: string) {
  if (wasDragging) return
  toggleSelect(id)
}

// Selection helpers
function toggleSelect(id: string) {
  const next = new Set(selectedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedIds.value = next
}

function selectAll() {
  selectedIds.value = new Set(pageSamples.value.map((s) => s.id))
}

function deselectAll() {
  selectedIds.value = new Set()
}

function applyLabel(label: string, ids: Set<string>) {
  if (ids.size === 0) return
  const draft = { ...labelDraft.value }
  ids.forEach((id) => {
    draft[id] = label
  })
  labelDraft.value = draft
}

function applyBulkLabel() {
  if (!bulkLabel.value) return
  applyLabel(bulkLabel.value, selectedIds.value)
}

// Keyboard shortcuts: 1-9 assign labelSpace[N-1] to selected samples
function onKeyDown(e: KeyboardEvent) {
  // Guard: skip when focus is in form elements
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

onMounted(() => {
  document.addEventListener('keydown', onKeyDown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeyDown)
  document.removeEventListener('mousemove', onDocMouseMove)
  document.removeEventListener('mouseup', onDocMouseUp)
})
</script>

<style scoped>
.classify-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  padding: 12px;
  box-sizing: border-box;
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

.classify-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(var(--cell-size, 128px), 1fr));
  gap: 8px;
  overflow-y: auto;
  flex: 1;
  padding: 8px;
  position: relative;
}

.classify-grid--dragging {
  user-select: none;
  -webkit-user-select: none;
}

.rubber-band-rect {
  position: absolute;
  border: 2px dashed #18a058;
  background: rgba(24, 160, 88, 0.1);
  pointer-events: none;
  z-index: 10;
}

.grid-cell {
  aspect-ratio: 1;
  position: relative;
  border-radius: 6px;
  overflow: hidden;
  cursor: pointer;
  border: 2px solid transparent;
  background: #f0f0f0;
}

.grid-cell img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.grid-cell--selected {
  border-color: #18a058 !important;
}

.cell-checkbox {
  position: absolute;
  top: 6px;
  left: 6px;
  width: 18px;
  height: 18px;
  border: 2px solid white;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.3);
  z-index: 2;
  pointer-events: auto;
  cursor: pointer;
}

.cell-checkbox--checked {
  background: #18a058;
  border-color: #18a058;
}

.cell-checkbox--checked::after {
  content: '✓';
  color: white;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}
</style>
