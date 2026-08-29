<template>
  <div class="sb" tabindex="-1">
    <!-- Label Rail (left) -->
    <div v-if="showLabelRail" class="sb-label-rail">
      <slot name="label-rail" />
    </div>

    <!-- Card grid (right) -->
    <div class="sb-grid-area">
      <div
        ref="scrollRef"
        class="sb-scroll-container"
        @mousedown="onMouseDown"
        @scroll="onContainerScroll"
      >
        <div
          :style="{
            height: virtualizer.getTotalSize() + 'px',
            position: 'relative',
            width: '100%',
          }"
        >
          <div
            v-for="vRow in virtualizer.getVirtualItems()"
            :key="`${layout}-${vRow.index}`"
            :style="{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: vRow.size + 'px',
              transform: `translateY(${vRow.start}px)`,
            }"
          >
            <div v-if="layout === 'grid'" class="sb-card-row">
              <div
                v-for="item in getRowItems(vRow.index)"
                :key="item.id"
                class="sb-card"
                :class="{
                  'sb-card--selected': selectedIds.has(item.id),
                  'sb-card--draft': !!(item.draftLabel || item.predictionLabel),
                }"
                :style="{ width: cardWidth + 'px' }"
                :data-item-id="item.id"
                data-sb-item
                :data-sb-id="item.id"
                @click.stop="onItemClick(item.id, $event)"
              >
                <label v-if="showCheckboxes" class="sb-select-box" @mousedown.stop @click.stop>
                  <input
                    type="checkbox"
                    :checked="selectedIds.has(item.id)"
                    @change="toggleSelection(item.id)"
                  />
                </label>
                <div class="sb-card-images" :style="{ height: thumbSize + 'px' }">
                  <img
                    v-for="(src, imgIdx) in item.imageSrcs"
                    :key="imgIdx"
                    :src="src"
                    loading="lazy"
                    alt=""
                    class="sb-card-img"
                    :style="{ height: thumbSize + 'px' }"
                  />
                </div>
                <div class="sb-card-footer">
                  <span
                    v-if="effectiveLabel(item)"
                    class="sb-badge"
                    :style="{ background: labelColor(effectiveLabel(item)!) }"
                    >{{ effectiveLabel(item) }}</span
                  >
                  <span v-else class="sb-badge sb-badge--empty">&mdash;</span>
                  <span v-if="item.predictionConfidence != null" class="sb-confidence"
                    >{{ (item.predictionConfidence * 100).toFixed(0) }}%</span
                  >
                </div>
              </div>
            </div>
            <div
              v-else-if="getListItem(vRow.index)"
              :key="getListItem(vRow.index)!.id"
              class="sb-list-row"
              :class="{
                'sb-list-row--selected': selectedIds.has(getListItem(vRow.index)!.id),
                'sb-list-row--draft': !!(
                  getListItem(vRow.index)!.draftLabel || getListItem(vRow.index)!.predictionLabel
                ),
                'sb-list-row--no-checkbox': !showCheckboxes,
              }"
              :data-item-id="getListItem(vRow.index)!.id"
              data-sb-item
              :data-sb-id="getListItem(vRow.index)!.id"
              @click.stop="onItemClick(getListItem(vRow.index)!.id, $event)"
            >
              <div v-if="showCheckboxes" class="sb-list-select">
                <label class="sb-select-box sb-select-box--inline" @mousedown.stop @click.stop>
                  <input
                    type="checkbox"
                    :checked="selectedIds.has(getListItem(vRow.index)!.id)"
                    @change="toggleSelection(getListItem(vRow.index)!.id)"
                  />
                </label>
              </div>
              <div class="sb-list-images" :style="{ minHeight: thumbSize + 'px' }">
                <img
                  v-for="(src, imgIdx) in getListItem(vRow.index)!.imageSrcs"
                  :key="imgIdx"
                  :src="src"
                  loading="lazy"
                  alt=""
                  class="sb-list-img"
                  :style="{ width: thumbSize + 'px', height: thumbSize + 'px' }"
                />
                <div v-if="getListItem(vRow.index)!.imageSrcs.length === 0" class="sb-list-empty">
                  {{ t("widgets.noImage") }}
                </div>
              </div>
              <div class="sb-list-main">
                <div class="sb-list-head">
                  <span class="sb-list-id">{{ getListItem(vRow.index)!.id }}</span>
                  <span
                    v-if="effectiveLabel(getListItem(vRow.index)!)"
                    class="sb-badge"
                    :style="{ background: labelColor(effectiveLabel(getListItem(vRow.index)!)!) }"
                    >{{ effectiveLabel(getListItem(vRow.index)!) }}</span
                  >
                  <span v-else class="sb-badge sb-badge--empty">&mdash;</span>
                  <span class="sb-list-image-count">{{
                    t("widgets.imageCount", {
                      count: getListItem(vRow.index)!.imageSrcs.length,
                    })
                  }}</span>
                  <span
                    v-if="getListItem(vRow.index)!.predictionConfidence != null"
                    class="sb-confidence"
                    >{{ (getListItem(vRow.index)!.predictionConfidence! * 100).toFixed(0) }}%</span
                  >
                </div>
                <div class="sb-list-meta">
                  {{ metadataPreview(getListItem(vRow.index)!.metadata) }}
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Rubber band overlay -->
        <div
          v-if="selectionEnabled && isDragging && rubberRect"
          class="sb-rubber-band"
          :style="{
            left: rubberRect.left + 'px',
            top: rubberRect.top + 'px',
            width: rubberRect.width + 'px',
            height: rubberRect.height + 'px',
          }"
        />

        <!-- Loading indicator -->
        <div v-if="isLoading" class="sb-loading">{{ t("widgets.loadingMore") }}</div>
      </div>

      <!-- Floating bottom bar -->
      <div v-if="showBottomBar" class="sb-bottom-bar">
        <div class="sb-bar-left">
          <slot name="bar-left" />
        </div>
        <div class="sb-bar-right">
          <span class="sb-bar-count">
            {{
              t("widgets.selectionLoaded", {
                selected: selectedIds.size,
                loaded: items.length,
                total: totalCount,
              })
            }}
          </span>
          <slot name="bar-right" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import { useVirtualizer } from "@tanstack/vue-virtual";
import { useI18n } from "vue-i18n";
import type { BrowserItem } from "@/shared/types/components";
import { handleBrowserActivation } from "./browser-activation";

const { t } = useI18n();

const props = withDefaults(
  defineProps<{
    items: BrowserItem[];
    totalCount: number;
    thumbSize?: number;
    layout?: "grid" | "list";
    isLoading?: boolean;
    selectionEnabled?: boolean;
    showCheckboxes?: boolean;
    showBottomBar?: boolean;
    showLabelRail?: boolean;
    activationMode?: "open" | "select";
  }>(),
  {
    thumbSize: 160,
    layout: "grid",
    isLoading: false,
    selectionEnabled: false,
    showCheckboxes: false,
    showBottomBar: false,
    showLabelRail: false,
    activationMode: "open",
  },
);

const emit = defineEmits<{
  "open-item": [id: string];
  select: [ids: Set<string>];
  "load-more": [];
}>();

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const LABEL_COLORS = [
  "#4CAF50",
  "#2196F3",
  "#FF9800",
  "#E91E63",
  "#9C27B0",
  "#00BCD4",
  "#FF5722",
  "#795548",
  "#607D8B",
  "#CDDC39",
];

// Basic hash for label color consistency
function labelColor(label: string): string {
  let hash = 0;
  for (let i = 0; i < label.length; i++) {
    hash = label.charCodeAt(i) + ((hash << 5) - hash);
  }
  const idx = Math.abs(hash) % LABEL_COLORS.length;
  return LABEL_COLORS[idx];
}

function effectiveLabel(item: BrowserItem): string | null {
  return item.draftLabel ?? item.predictionLabel ?? item.currentLabel ?? null;
}

function metadataPreview(metadata: Record<string, unknown>): string {
  const preview = JSON.stringify(metadata);
  if (!preview || preview === "{}") return "No metadata";
  return preview.length > 180 ? `${preview.slice(0, 180)}...` : preview;
}

// ---------------------------------------------------------------------------
// Grid layout
// ---------------------------------------------------------------------------

const scrollRef = ref<HTMLElement | null>(null);
const containerWidth = ref(800);
const cardWidth = computed(() => props.thumbSize + 20);
const cardsPerRow = computed(() => Math.max(1, Math.floor(containerWidth.value / cardWidth.value)));
const rowCount = computed(() => Math.ceil(props.items.length / cardsPerRow.value));
const layout = computed(() => props.layout);

function getRowItems(rowIndex: number): BrowserItem[] {
  const start = rowIndex * cardsPerRow.value;
  return props.items.slice(start, start + cardsPerRow.value);
}

function getListItem(index: number): BrowserItem | undefined {
  return props.items[index];
}

// ---------------------------------------------------------------------------
// Selection
// ---------------------------------------------------------------------------

const selectedIds = ref<Set<string>>(new Set());

function emitSelection() {
  emit("select", selectedIds.value);
}

function toggleSelection(id: string) {
  if (!props.selectionEnabled) return;
  const next = new Set(selectedIds.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  selectedIds.value = next;
  emitSelection();
}

function onItemClick(id: string, e: MouseEvent) {
  if (wasDragging) return;

  handleBrowserActivation(props.activationMode, id, e, {
    onOpen: (targetId) => {
      emit("open-item", targetId);
      // Even in 'open' mode, we might allow multi-select if explicitly enabled
      if (props.selectionEnabled && (e.ctrlKey || e.metaKey)) {
        toggleSelection(targetId);
      }
    },
    onSelect: (targetId, multi) => {
      if (!props.selectionEnabled) return;
      if (multi) {
        toggleSelection(targetId);
      } else {
        selectedIds.value = new Set([targetId]);
        emitSelection();
      }
    },
  });
}

// ---------------------------------------------------------------------------
// Virtualizer
// ---------------------------------------------------------------------------

const rowHeight = computed(() => {
  if (layout.value === "list") return props.thumbSize + 56;
  return props.thumbSize + 48;
});

const virtualizer = useVirtualizer({
  get count() {
    return layout.value === "list" ? props.items.length : rowCount.value;
  },
  getScrollElement: () => scrollRef.value,
  estimateSize: () => rowHeight.value,
  overscan: 3,
});

// Trigger load-more when scrolling near the bottom
function onContainerScroll() {
  const el = scrollRef.value;
  if (!el) return;
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 200) {
    emit("load-more");
  }
}

// Watch virtual items for load-more
watch(
  () => virtualizer.value.getVirtualItems(),
  (items) => {
    if (!items.length) return;
    const lastItem = items[items.length - 1];
    const threshold = layout.value === "list" ? props.items.length - 2 : rowCount.value - 2;
    if (lastItem && lastItem.index >= threshold) {
      emit("load-more");
    }
  },
);

// ---------------------------------------------------------------------------
// Rubber-band selection
// ---------------------------------------------------------------------------

const isDragging = ref(false);
const dragStart = ref<{ x: number; y: number } | null>(null);
const dragCurrent = ref<{ x: number; y: number } | null>(null);
const DRAG_THRESHOLD = 5;
let wasDragging = false;
let dragCtrlHeld = false;
let autoScrollTimer: ReturnType<typeof setInterval> | null = null;

const rubberRect = computed(() => {
  if (!dragStart.value || !dragCurrent.value || !scrollRef.value) return null;
  const rect = scrollRef.value.getBoundingClientRect();
  const x1 = Math.min(dragStart.value.x, dragCurrent.value.x) - rect.left;
  const y1 =
    Math.min(dragStart.value.y, dragCurrent.value.y) - rect.top + scrollRef.value.scrollTop;
  const x2 = Math.max(dragStart.value.x, dragCurrent.value.x) - rect.left;
  const y2 =
    Math.max(dragStart.value.y, dragCurrent.value.y) - rect.top + scrollRef.value.scrollTop;
  return { left: x1, top: y1, width: x2 - x1, height: y2 - y1 };
});

function onMouseDown(e: MouseEvent) {
  if (!props.selectionEnabled) return;
  if (e.button !== 0) return;
  if ((e.target as HTMLElement).closest(".sb-label-rail, .sb-bottom-bar, button, input")) return;
  e.preventDefault();
  dragStart.value = { x: e.clientX, y: e.clientY };
  dragCurrent.value = { x: e.clientX, y: e.clientY };
  dragCtrlHeld = e.ctrlKey || e.metaKey;
  document.addEventListener("mousemove", onDocMouseMove);
  document.addEventListener("mouseup", onDocMouseUp);
}

function onDocMouseMove(e: MouseEvent) {
  if (!dragStart.value) return;
  dragCurrent.value = { x: e.clientX, y: e.clientY };
  const dx = e.clientX - dragStart.value.x;
  const dy = e.clientY - dragStart.value.y;
  if (!isDragging.value && Math.sqrt(dx * dx + dy * dy) >= DRAG_THRESHOLD) {
    isDragging.value = true;
    startAutoScroll();
  }
  if (isDragging.value) {
    updateRubberBandSelection();
  }
}

function onDocMouseUp() {
  document.removeEventListener("mousemove", onDocMouseMove);
  document.removeEventListener("mouseup", onDocMouseUp);
  stopAutoScroll();

  if (isDragging.value) {
    updateRubberBandSelection();
    wasDragging = true;
    setTimeout(() => {
      wasDragging = false;
    }, 0);
  }

  isDragging.value = false;
  dragStart.value = null;
  dragCurrent.value = null;
}

function updateRubberBandSelection() {
  if (!rubberRect.value || !scrollRef.value) return;
  const rr = rubberRect.value;
  const rrBottom = rr.top + rr.height;

  // Find all card elements that intersect the rubber band
  const cards = scrollRef.value.querySelectorAll<HTMLElement>("[data-item-id]");
  const intersecting: string[] = [];
  const containerRect = scrollRef.value.getBoundingClientRect();
  const scrollTop = scrollRef.value.scrollTop;

  for (const card of cards) {
    const cardRect = card.getBoundingClientRect();
    const cardTop = cardRect.top - containerRect.top + scrollTop;
    const cardBottom = cardTop + cardRect.height;
    const cardLeft = cardRect.left - containerRect.left;
    const cardRight = cardLeft + cardRect.width;

    if (
      cardBottom >= rr.top &&
      cardTop <= rrBottom &&
      cardRight >= rr.left &&
      cardLeft <= rr.left + rr.width
    ) {
      const id = card.dataset.itemId;
      if (id) intersecting.push(id);
    }
  }

  if (dragCtrlHeld) {
    const next = new Set(selectedIds.value);
    intersecting.forEach((id) => next.add(id));
    selectedIds.value = next;
  } else {
    selectedIds.value = new Set(intersecting);
  }
  emitSelection();
}

// Auto-scroll when drag reaches viewport edges
function startAutoScroll() {
  if (autoScrollTimer) return;
  autoScrollTimer = setInterval(() => {
    if (!isDragging.value || !dragCurrent.value || !scrollRef.value) return;
    const rect = scrollRef.value.getBoundingClientRect();
    const edgeZone = 40;
    const speed = 12;
    if (dragCurrent.value.y < rect.top + edgeZone) {
      scrollRef.value.scrollTop -= speed;
    } else if (dragCurrent.value.y > rect.bottom - edgeZone) {
      scrollRef.value.scrollTop += speed;
    }
  }, 16);
}

function stopAutoScroll() {
  if (autoScrollTimer) {
    clearInterval(autoScrollTimer);
    autoScrollTimer = null;
  }
}

// ---------------------------------------------------------------------------
// Container resize observer
// ---------------------------------------------------------------------------

let resizeObserver: ResizeObserver | null = null;

onMounted(() => {
  if (scrollRef.value) {
    containerWidth.value = scrollRef.value.clientWidth;
    resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        containerWidth.value = entry.contentRect.width;
      }
    });
    resizeObserver.observe(scrollRef.value);
  }
});

onUnmounted(() => {
  stopAutoScroll();
  document.removeEventListener("mousemove", onDocMouseMove);
  document.removeEventListener("mouseup", onDocMouseUp);
  if (resizeObserver) {
    resizeObserver.disconnect();
    resizeObserver = null;
  }
});

// ---------------------------------------------------------------------------
// Expose for parent ref access
// ---------------------------------------------------------------------------

defineExpose({
  selectedIds,
  clearSelection: () => {
    selectedIds.value = new Set();
    emitSelection();
  },
});
</script>

<style scoped>
.sb {
  display: flex;
  width: 100%;
  height: 100%;
  min-height: 0;
  outline: none;
}

/* Label rail */
.sb-label-rail {
  display: flex;
  flex-direction: column;
  width: 170px;
  min-width: 170px;
  border-right: 1px solid var(--cv-border, rgba(255, 255, 255, 0.12));
  background: var(--cv-card-bg, #1e1e2e);
}

/* Grid area */
.sb-grid-area {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.sb-scroll-container {
  flex: 1;
  overflow-y: auto;
  position: relative;
  padding: 8px;
}

.sb-scroll-container::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
.sb-scroll-container::-webkit-scrollbar-track {
  background: transparent;
}
.sb-scroll-container::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
}
.sb-scroll-container::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.2);
}

.sb-card-row {
  display: flex;
  gap: 8px;
  flex-wrap: nowrap;
}

.sb-card {
  position: relative;
  flex-shrink: 0;
  border: 2px solid transparent;
  border-radius: 6px;
  background: var(--cv-card-bg, #1e1e2e);
  cursor: pointer;
  overflow: hidden;
  transition: border-color 0.1s;
}

.sb-card:hover {
  border-color: var(--cv-border, rgba(255, 255, 255, 0.2));
}

.sb-select-box {
  position: absolute;
  top: 8px;
  left: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--cv-card-bg, #1e1e2e) 88%, black);
  z-index: 2;
}

.sb-select-box--inline {
  position: static;
  background: transparent;
  width: auto;
  height: auto;
}

.sb-select-box input {
  margin: 0;
}

.sb-card--selected {
  border-color: var(--cv-primary, #4098fc) !important;
  box-shadow: 0 0 0 1px var(--cv-primary, #4098fc);
}

.sb-card-images {
  display: flex;
  overflow: hidden;
  background: #111;
}

.sb-card-img {
  width: 100%;
  object-fit: cover;
  flex-shrink: 0;
}

.sb-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 6px;
  min-height: 24px;
}

.sb-badge {
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

.sb-badge--empty {
  background: transparent;
  color: var(--cv-text-disabled, rgba(255, 255, 255, 0.3));
}

.sb-confidence {
  font-size: 10px;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.5));
  flex-shrink: 0;
}

.sb-list-row {
  display: grid;
  grid-template-columns: 28px minmax(0, auto) minmax(0, 1fr);
  gap: 12px;
  align-items: start;
  padding: 12px;
  border: 1px solid var(--cv-border, rgba(255, 255, 255, 0.12));
  border-radius: 10px;
  background: var(--cv-card-bg, #1e1e2e);
  cursor: pointer;
}

.sb-list-row--no-checkbox {
  grid-template-columns: minmax(0, auto) minmax(0, 1fr);
}

.sb-list-row--selected {
  border-color: var(--cv-primary, #4098fc);
  box-shadow: 0 0 0 1px var(--cv-primary, #4098fc);
}

.sb-list-select {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 2px;
}

.sb-list-images {
  display: flex;
  gap: 8px;
  min-width: 0;
  overflow-x: auto;
}

.sb-list-img {
  object-fit: cover;
  border-radius: 8px;
  background: #111;
  flex-shrink: 0;
}

.sb-list-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 120px;
  min-height: 80px;
  border: 1px dashed var(--cv-border, rgba(255, 255, 255, 0.12));
  border-radius: 8px;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.5));
  font-size: 12px;
}

.sb-list-main {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.sb-list-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.sb-list-id {
  font-family: monospace;
  font-size: 12px;
  color: var(--cv-text, #fff);
  word-break: break-all;
}

.sb-list-image-count {
  font-size: 11px;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.5));
}

.sb-list-meta {
  font-size: 12px;
  line-height: 1.5;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.5));
  word-break: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Rubber band */
.sb-rubber-band {
  position: absolute;
  border: 2px dashed var(--cv-primary, #4098fc);
  background: color-mix(in srgb, var(--cv-primary, #4098fc) 15%, transparent);
  pointer-events: none;
  z-index: 10;
}

/* Bottom bar */
.sb-bottom-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-top: 1px solid var(--cv-border, rgba(255, 255, 255, 0.12));
  background: var(--cv-card-bg, #1e1e2e);
  flex-shrink: 0;
}

.sb-bar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sb-bar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.sb-bar-count {
  font-size: 12px;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.5));
}

/* Loading */
.sb-loading {
  padding: 12px;
  text-align: center;
  font-size: 12px;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.5));
}

@media (max-width: 900px) {
  .sb-list-row {
    grid-template-columns: 28px minmax(0, 1fr);
  }

  .sb-list-row--no-checkbox {
    grid-template-columns: minmax(0, 1fr);
  }

  .sb-list-main {
    grid-column: 1 / -1;
  }
}
</style>
