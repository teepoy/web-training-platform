<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from "vue";
import type { CSSProperties } from "vue";
import {
  NSwitch,
  NText,
  NRadioGroup,
  NRadioButton,
  NButton,
  NTag,
  NSelect,
  NModal,
  NCheckboxGroup,
  NCheckbox,
} from "naive-ui";
import type { ScSampleItem } from "@/features/sc/generated/proto/sc/v1/sample_pb";
import { withAuthQueryParams } from "@/shared/api/client";
import { useBlinkController } from "../../composables/useBlinkController";
import {
  useBlinkVirtualScroll,
  ROW_PADDING_Y,
  MINI_HEADER_HEIGHT,
} from "@/features/sc/presentation/composables/useBlinkVirtualScroll";
import { useBlinkRubberBand } from "@/features/sc/presentation/composables/useBlinkRubberBand";

const props = withDefaults(
  defineProps<{
    samples: ScSampleItem[];
    reviewSamples?: ScSampleItem[];
    reviewLoading?: boolean;
    reviewError?: string | null;
    patchSamplesPerRow?: number;
    reviewSamplesPerRow?: number;
    patchCellSize?: number;
    reviewCellSize?: number;
    cellGap?: number;
    rowGap?: number;
    selectedDefectIds?: Set<string> | string[];
    predictionLabels?: Record<string, string>;
    predictionConfidences?: Record<string, number | null>;
    annotationLabels?: Record<string, string>;
    annotationDrafts?: Record<string, string>;
    showPredictionBadges?: boolean;
    overscan?: number;
    blinkIntervalMs?: number;
    initialBlinkEnabled?: boolean;
    showModeSwitch?: boolean;
    inspectionTime?: string;
  }>(),
  {
    patchSamplesPerRow: 3,
    reviewSamplesPerRow: 1,
    patchCellSize: 64,
    reviewCellSize: 128,
    cellGap: 4,
    rowGap: 12,
    selectedDefectIds: () => new Set<string>(),
    predictionLabels: () => ({}),
    predictionConfidences: () => ({}),
    annotationLabels: () => ({}),
    annotationDrafts: () => ({}),
    showPredictionBadges: false,
    overscan: 10,
    blinkIntervalMs: 1000,
    initialBlinkEnabled: true,
    showModeSwitch: false,
  }
);

const emit = defineEmits<{
  selectSamples: [
    defectIds: string[],
    modifiers: {
      shift: boolean;
      ctrl: boolean;
      meta: boolean;
      selectionMode?: "replace" | "add" | "toggle";
    }
  ];
  scrollContainerChange: [element: HTMLElement | null];
}>();

const mode = ref<"patch" | "review">("patch");
const settingsOpen = ref(false);
const MAX_SAMPLES_PER_ROW = 6;
const clampSamplesPerRow = (value: number): number =>
  Math.min(MAX_SAMPLES_PER_ROW, Math.max(1, value));
const patchPerRow = ref(clampSamplesPerRow(props.patchSamplesPerRow));
const reviewPerRow = ref(clampSamplesPerRow(props.reviewSamplesPerRow));
const IMAGE_SIZE_OPTIONS = [32, 64, 128, 256, 512] as const;
const IMAGE_SIZE_SELECT_OPTIONS = IMAGE_SIZE_OPTIONS.map((size) => ({
  label: `${size}`,
  value: size,
}));
type ImageSizeOption = (typeof IMAGE_SIZE_OPTIONS)[number];
type PatchImageType = "defective" | "template" | "difference";
const PATCH_IMAGE_TYPE_OPTIONS: Array<{ label: string; value: PatchImageType }> = [
  { label: "Defective", value: "defective" },
  { label: "Reference", value: "template" },
  { label: "Difference", value: "difference" },
];
const PATCH_IMAGE_LABELS: Record<PatchImageType, string> = {
  defective: "Defective",
  template: "Reference",
  difference: "Difference",
};
const DEFAULT_PATCH_IMAGE_TYPES: PatchImageType[] = ["defective", "template", "difference"];
const normalizeImageSize = (value: number | undefined): ImageSizeOption =>
  IMAGE_SIZE_OPTIONS.includes(value as ImageSizeOption)
    ? (value as ImageSizeOption)
    : 64;
const patchImageSize = ref<ImageSizeOption>(normalizeImageSize(props.patchCellSize));
const reviewImageSize = ref<ImageSizeOption>(normalizeImageSize(props.reviewCellSize));
const selectedPatchImageTypes = ref<PatchImageType[]>([...DEFAULT_PATCH_IMAGE_TYPES]);
const imageSize = computed({
  get: () => mode.value === "patch" ? patchImageSize.value : reviewImageSize.value,
  set: (value: number) => {
    const normalized = normalizeImageSize(value);
    if (mode.value === "patch") {
      patchImageSize.value = normalized;
    } else {
      reviewImageSize.value = normalized;
    }
  },
});
const samplesPerRow = computed({
  get: () => mode.value === "patch" ? patchPerRow.value : reviewPerRow.value,
  set: (value: number) => {
    if (mode.value === "patch") {
      patchPerRow.value = clampSamplesPerRow(value);
    } else {
      reviewPerRow.value = clampSamplesPerRow(value);
    }
  },
});

function adjustSamplesPerRow(delta: number): void {
  samplesPerRow.value += delta;
}

const reviewDisabled = computed(
  () => props.reviewLoading || !!props.reviewError || (props.reviewSamples ?? []).length === 0,
);

watch(() => props.patchSamplesPerRow, (v) => {
  patchPerRow.value = clampSamplesPerRow(v);
});
watch(() => props.reviewSamplesPerRow, (v) => {
  reviewPerRow.value = clampSamplesPerRow(v);
});
watch(() => props.patchCellSize, (v) => {
  patchImageSize.value = normalizeImageSize(v);
});
watch(() => props.reviewCellSize, (v) => {
  reviewImageSize.value = normalizeImageSize(v);
});
watch(reviewDisabled, (disabled) => {
  if (disabled && mode.value === "review") mode.value = "patch";
});
watch(selectedPatchImageTypes, (types) => {
  if (types.length === 0) selectedPatchImageTypes.value = [...DEFAULT_PATCH_IMAGE_TYPES];
});

const samplesRef = computed(() =>
  mode.value === "review" ? props.reviewSamples ?? [] : props.samples,
);
const patchCellSizeRef = patchImageSize;
const reviewCellSizeRef = reviewImageSize;
const overscanRef = computed(() => props.overscan);
const PREDICTION_BADGE_ROW_HEIGHT = 26;
const extraRowHeight = computed(() =>
  props.showPredictionBadges ? PREDICTION_BADGE_ROW_HEIGHT : 0,
);
const {
  virtualizer,
  virtualRowHeightStr,
  shouldLoadImages,
  queueViewportImageLoad,
  scrollRef,
  visibleSamples,
  imageCellHeightPxStr,
  samplesForVirtualRow,
  effectiveSamplesPerRow,
} = useBlinkVirtualScroll({
  samples: samplesRef,
  mode,
  patchPerRow,
  reviewPerRow,
  patchCellSize: patchCellSizeRef,
  reviewCellSize: reviewCellSizeRef,
  extraRowHeight,
  overscan: overscanRef,
});

watch(scrollRef, (element) => emit("scrollContainerChange", element), {
  immediate: true,
  flush: "post",
});

const cellSize = computed(() =>
  mode.value === "patch" ? patchImageSize.value : reviewImageSize.value
);

function reviewImageCount(sample: ScSampleItem): number {
  return Array.isArray(sample.reviewImages) ? sample.reviewImages.length : 0;
}

const { enabled: blinkEnabled, phase: blinkPhase, toggle: toggleBlink } = useBlinkController({
  intervalMs: props.blinkIntervalMs,
  initialEnabled: props.initialBlinkEnabled,
});

const patchImageTypesForSprite = computed<PatchImageType[]>(() => {
  const requested = [...selectedPatchImageTypes.value];
  if (blinkEnabled.value) {
    for (const required of ["template", "defective"] as PatchImageType[]) {
      if (!requested.includes(required)) requested.unshift(required);
    }
  }
  return DEFAULT_PATCH_IMAGE_TYPES.filter((type) => requested.includes(type));
});

const basePatchColumns = computed(() =>
  selectedPatchImageTypes.value.map((type) => ({
    label: PATCH_IMAGE_LABELS[type],
    spriteIndex: patchImageTypesForSprite.value.indexOf(type),
    type,
  })).filter((column) => column.spriteIndex >= 0),
);

function reviewColumnsForSample(sample: ScSampleItem): number[] {
  return Array.from({ length: reviewImageCount(sample) }, (_, i) => i).filter(
    (index) => selectedReviewImageIndexes.value.includes(index),
  );
}

const maxReviewImageCount = computed(() => {
  if (mode.value !== "review") return 0;
  return visibleSamples.value.reduce(
    (max, sample) => Math.max(max, reviewImageCount(sample)),
    0,
  );
});

const reviewImageOptions = computed(() =>
  Array.from({ length: maxReviewImageCount.value }, (_, index) => ({
    label: `Rev ${index + 1}`,
    value: index,
  })),
);
const selectedReviewImageIndexes = ref<number[]>([]);
watch(maxReviewImageCount, (count) => {
  const all = Array.from({ length: count }, (_, index) => index);
  selectedReviewImageIndexes.value =
    selectedReviewImageIndexes.value.length === 0
      ? all
      : selectedReviewImageIndexes.value.filter((index) => index < count);
}, { immediate: true });

function cellsForSample(sample: ScSampleItem): number {
  const imageCells = basePatchColumns.value.length +
    (mode.value === "review" ? reviewColumnsForSample(sample).length : 0);
  return imageCells + (blinkEnabled.value ? 1 : 0);
}

const maxCellsPerSample = computed(() =>
  basePatchColumns.value.length +
  (mode.value === "review" ? selectedReviewImageIndexes.value.length : 0) +
  (blinkEnabled.value ? 1 : 0),
);

const SAMPLE_BLOCK_PADDING_X = 4;

function sampleBlockWidthPx(sample: ScSampleItem): number {
  const cells = cellsForSample(sample);
  return cells * cellSize.value + Math.max(0, cells - 1) * props.cellGap + SAMPLE_BLOCK_PADDING_X;
}

const maxSampleBlockWidthPx = computed(() =>
  maxCellsPerSample.value * cellSize.value +
  Math.max(0, maxCellsPerSample.value - 1) * props.cellGap +
  SAMPLE_BLOCK_PADDING_X,
);

const rowMinWidthPx = computed(
  () =>
    effectiveSamplesPerRow.value * maxSampleBlockWidthPx.value +
    (effectiveSamplesPerRow.value - 1) * props.rowGap +
    24 /* left+right row padding */
);
const cellSizePx = computed(() => `${cellSize.value}px`);
function sampleBlockWidthStr(sample: ScSampleItem): string {
  return `${sampleBlockWidthPx(sample)}px`;
}
const rowMinWidthStr = computed(() => `${rowMinWidthPx.value}px`);

const {
  rubberBandStyle,
  onMouseDown,
} = useBlinkRubberBand({
  scrollRef,
  onSelect: (ids, mods) => emit("selectSamples", ids, mods),
});

const requestedSpriteUrls = ref<Set<string>>(new Set());

function isSelected(defectId: number | string): boolean {
  const idStr = defectIdKey(defectId);
  if (props.selectedDefectIds instanceof Set) {
    return props.selectedDefectIds.has(idStr);
  }
  return props.selectedDefectIds.includes(idStr);
}

function defectIdKey(defectId: number | string): string {
  return String(defectId);
}

const selectionAnchorId = ref<string | null>(null);
const orderedVisibleDefectIds = computed(() =>
  visibleSamples.value.map((sample) => defectIdKey(sample.defectId)),
);

function rangeBetween(anchorId: string, targetId: string): string[] {
  const ids = orderedVisibleDefectIds.value;
  const anchorIndex = ids.indexOf(anchorId);
  const targetIndex = ids.indexOf(targetId);
  if (anchorIndex < 0 || targetIndex < 0) return [targetId];
  const start = Math.min(anchorIndex, targetIndex);
  const end = Math.max(anchorIndex, targetIndex);
  return ids.slice(start, end + 1);
}

function handleSampleClick(sample: ScSampleItem, event: MouseEvent): void {
  const targetId = defectIdKey(sample.defectId);
  const ctrlOrMeta = event.ctrlKey || event.metaKey;
  if (event.shiftKey) {
    const anchor = selectionAnchorId.value ?? targetId;
    emit("selectSamples", rangeBetween(anchor, targetId), {
      shift: true,
      ctrl: event.ctrlKey,
      meta: event.metaKey,
      selectionMode: ctrlOrMeta ? "add" : "replace",
    });
    return;
  }

  selectionAnchorId.value = targetId;
  emit("selectSamples", [targetId], {
    shift: false,
    ctrl: event.ctrlKey,
    meta: event.metaKey,
    selectionMode: ctrlOrMeta ? "toggle" : "replace",
  });
}

function getSpriteUrl(sample: ScSampleItem): string {
  const isPatch = mode.value === "patch";
  const cs = isPatch ? patchImageSize.value : reviewImageSize.value;
  const t = props.inspectionTime ?? String(sample.inspectionTime);
  const params = new URLSearchParams();
  params.set("cell_size", String(cs));
  for (const type of patchImageTypesForSprite.value) {
    params.append("image_types", type);
  }
  if (!isPatch) {
    params.set("review_count", String(reviewImageCount(sample)));
  }
  const spriteMode = isPatch ? "patch" : "review";
  return `/api/v1/sc/sprites/${spriteMode}/${t}/${sample.waferKey}/${sample.defectId}?${params.toString()}`;
}

function shouldRenderSprite(sample: ScSampleItem): boolean {
  const url = getSpriteUrl(sample);
  if (shouldLoadImages.value) {
    requestedSpriteUrls.value.add(url);
    return true;
  }
  return requestedSpriteUrls.value.has(url);
}

function getSpriteStyle(sample: ScSampleItem, colIndex: number) {
  const isPatch = mode.value === "patch";
  const cols = patchImageTypesForSprite.value.length + (isPatch ? 0 : reviewImageCount(sample));
  const url = getSpriteUrl(sample);

  const bgSize = `${cols * 100}% 100%`;
  const bgPos = cols > 1 ? `${(colIndex / (cols - 1)) * 100}% 0` : '0 0';

  return {
    backgroundImage: `url(${withAuthQueryParams(url)})`,
    backgroundSize: bgSize,
    backgroundPosition: bgPos,
    backgroundRepeat: 'no-repeat',
  };
}

function blinkBaseSpriteIndex(): number {
  const referenceIndex = patchImageTypesForSprite.value.indexOf("template");
  return referenceIndex >= 0 ? referenceIndex : 0;
}

function blinkOverlaySpriteIndex(): number {
  const defectiveIndex = patchImageTypesForSprite.value.indexOf("defective");
  return defectiveIndex >= 0 ? defectiveIndex : 0;
}

interface ScrollMetrics {
  clientWidth: number;
  clientHeight: number;
  scrollWidth: number;
  scrollHeight: number;
  scrollLeft: number;
  scrollTop: number;
}

const MIN_SCROLL_THUMB_SIZE = 24;
const scrollMetrics = ref<ScrollMetrics>({
  clientWidth: 0,
  clientHeight: 0,
  scrollWidth: 0,
  scrollHeight: 0,
  scrollLeft: 0,
  scrollTop: 0,
});
let resizeObserver: ResizeObserver | null = null;
let dragState:
  | {
      axis: "x" | "y";
      startPointer: number;
      startScroll: number;
      scrollableDistance: number;
      trackDistance: number;
    }
  | null = null;

const showYScrollbar = computed(
  () => scrollMetrics.value.scrollHeight > scrollMetrics.value.clientHeight + 1,
);
const showXScrollbar = computed(
  () => scrollMetrics.value.scrollWidth > scrollMetrics.value.clientWidth + 1,
);

const yThumbSize = computed(() => {
  const { clientHeight, scrollHeight } = scrollMetrics.value;
  if (clientHeight <= 0 || scrollHeight <= 0) return 0;
  return Math.min(
    clientHeight,
    Math.max(MIN_SCROLL_THUMB_SIZE, (clientHeight / scrollHeight) * clientHeight),
  );
});

const xThumbSize = computed(() => {
  const { clientWidth, scrollWidth } = scrollMetrics.value;
  if (clientWidth <= 0 || scrollWidth <= 0) return 0;
  return Math.min(
    clientWidth,
    Math.max(MIN_SCROLL_THUMB_SIZE, (clientWidth / scrollWidth) * clientWidth),
  );
});

const yThumbOffset = computed(() => {
  const { clientHeight, scrollHeight, scrollTop } = scrollMetrics.value;
  const scrollableDistance = scrollHeight - clientHeight;
  const trackDistance = clientHeight - yThumbSize.value;
  if (scrollableDistance <= 0 || trackDistance <= 0) return 0;
  return (scrollTop / scrollableDistance) * trackDistance;
});

const xThumbOffset = computed(() => {
  const { clientWidth, scrollWidth, scrollLeft } = scrollMetrics.value;
  const scrollableDistance = scrollWidth - clientWidth;
  const trackDistance = clientWidth - xThumbSize.value;
  if (scrollableDistance <= 0 || trackDistance <= 0) return 0;
  return (scrollLeft / scrollableDistance) * trackDistance;
});

const yThumbStyle = computed<CSSProperties>(() => ({
  height: `${yThumbSize.value}px`,
  transform: `translateY(${yThumbOffset.value}px)`,
}));

const xThumbStyle = computed<CSSProperties>(() => ({
  width: `${xThumbSize.value}px`,
  transform: `translateX(${xThumbOffset.value}px)`,
}));

function syncScrollMetrics(): void {
  const element = scrollRef.value;
  if (!element) return;
  scrollMetrics.value = {
    clientWidth: element.clientWidth,
    clientHeight: element.clientHeight,
    scrollWidth: element.scrollWidth,
    scrollHeight: element.scrollHeight,
    scrollLeft: element.scrollLeft,
    scrollTop: element.scrollTop,
  };
}

function attachResizeObserver(element: HTMLElement | null): void {
  resizeObserver?.disconnect();
  resizeObserver = null;
  if (!element || typeof ResizeObserver === "undefined") return;
  resizeObserver = new ResizeObserver(() => syncScrollMetrics());
  resizeObserver.observe(element);
  const content = element.firstElementChild;
  if (content instanceof HTMLElement) {
    resizeObserver.observe(content);
  }
}

watch(scrollRef, (element) => {
  attachResizeObserver(element);
  void nextTick(syncScrollMetrics);
}, { flush: "post" });

watch(
  [
    () => visibleSamples.value.length,
    rowMinWidthPx,
    virtualRowHeightStr,
    imageSize,
    selectedPatchImageTypes,
    selectedReviewImageIndexes,
    blinkEnabled,
  ],
  () => {
    void nextTick(syncScrollMetrics);
  },
  { flush: "post" },
);

function handleScroll(): void {
  queueViewportImageLoad();
  syncScrollMetrics();
}

function beginScrollbarDrag(axis: "x" | "y", event: MouseEvent): void {
  const element = scrollRef.value;
  if (!element) return;
  const metrics = scrollMetrics.value;
  const scrollableDistance =
    axis === "y"
      ? metrics.scrollHeight - metrics.clientHeight
      : metrics.scrollWidth - metrics.clientWidth;
  const trackDistance =
    axis === "y"
      ? metrics.clientHeight - yThumbSize.value
      : metrics.clientWidth - xThumbSize.value;
  if (scrollableDistance <= 0 || trackDistance <= 0) return;
  dragState = {
    axis,
    startPointer: axis === "y" ? event.clientY : event.clientX,
    startScroll: axis === "y" ? element.scrollTop : element.scrollLeft,
    scrollableDistance,
    trackDistance,
  };
  document.addEventListener("mousemove", handleScrollbarDrag);
  document.addEventListener("mouseup", endScrollbarDrag, { once: true });
}

function handleScrollbarDrag(event: MouseEvent): void {
  const element = scrollRef.value;
  if (!element || !dragState) return;
  const pointer = dragState.axis === "y" ? event.clientY : event.clientX;
  const delta = pointer - dragState.startPointer;
  const scrollDelta = (delta / dragState.trackDistance) * dragState.scrollableDistance;
  if (dragState.axis === "y") {
    element.scrollTop = dragState.startScroll + scrollDelta;
  } else {
    element.scrollLeft = dragState.startScroll + scrollDelta;
  }
  syncScrollMetrics();
}

function endScrollbarDrag(): void {
  dragState = null;
  document.removeEventListener("mousemove", handleScrollbarDrag);
}

function jumpScrollbar(axis: "x" | "y", event: MouseEvent): void {
  const element = scrollRef.value;
  if (!element) return;
  const target = event.currentTarget;
  if (!(target instanceof HTMLElement)) return;
  const rect = target.getBoundingClientRect();
  if (axis === "y") {
    const offset = event.clientY - rect.top - yThumbSize.value / 2;
    const trackDistance = scrollMetrics.value.clientHeight - yThumbSize.value;
    if (trackDistance > 0) {
      element.scrollTop =
        (offset / trackDistance) *
        (scrollMetrics.value.scrollHeight - scrollMetrics.value.clientHeight);
    }
  } else {
    const offset = event.clientX - rect.left - xThumbSize.value / 2;
    const trackDistance = scrollMetrics.value.clientWidth - xThumbSize.value;
    if (trackDistance > 0) {
      element.scrollLeft =
        (offset / trackDistance) *
        (scrollMetrics.value.scrollWidth - scrollMetrics.value.clientWidth);
    }
  }
  syncScrollMetrics();
}

onMounted(() => {
  window.addEventListener("resize", syncScrollMetrics);
  void nextTick(syncScrollMetrics);
});

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  document.removeEventListener("mousemove", handleScrollbarDrag);
  window.removeEventListener("resize", syncScrollMetrics);
});

defineExpose({ scrollRef });
</script>

<template>
  <div class="sbt">
    <!-- Toolbar -->
    <div class="sbt-toolbar">
      <div class="sbt-toolbar-left">
        <n-switch
          :value="blinkEnabled"
          size="small"
          @update:value="toggleBlink"
        />
        <n-text class="sbt-blink-label">Blink</n-text>

        <n-radio-group
          v-if="showModeSwitch"
          v-model:value="mode"
          size="small"
          class="sbt-mode-radio"
        >
          <n-radio-button value="patch">Patch</n-radio-button>
          <n-radio-button value="review" :disabled="reviewDisabled">Review</n-radio-button>
        </n-radio-group>

        <n-text v-if="reviewLoading" depth="3" class="sbt-review-status">
          Loading review...
        </n-text>
        <n-text v-else-if="reviewError" type="error" class="sbt-review-status">
          Review unavailable
        </n-text>

        <n-button size="tiny" quaternary @click="settingsOpen = true">
          Settings
        </n-button>
      </div>
      <div class="sbt-toolbar-right">
        <n-text class="sbt-row-count" depth="3">
          {{ visibleSamples.length }} samples
        </n-text>
      </div>
    </div>

    <n-modal
      v-model:show="settingsOpen"
      preset="card"
      title="Table Settings"
      class="sbt-settings-modal"
      :style="{ width: '380px' }"
    >
      <div class="sbt-settings">
        <div class="sbt-setting-row">
          <n-text class="sbt-control-label">Per Row</n-text>
          <div class="sbt-per-row">
            <n-button
              size="tiny"
              quaternary
              class="sbt-per-row-button"
              aria-label="Decrease samples per row"
              :disabled="samplesPerRow <= 1"
              @click="adjustSamplesPerRow(-1)"
            >
              &minus;
            </n-button>
            <n-text class="sbt-per-row-value" aria-live="polite">
              {{ samplesPerRow }}
            </n-text>
            <n-button
              size="tiny"
              quaternary
              class="sbt-per-row-button"
              aria-label="Increase samples per row"
              :disabled="samplesPerRow >= MAX_SAMPLES_PER_ROW"
              @click="adjustSamplesPerRow(1)"
            >
              +
            </n-button>
          </div>
        </div>

        <div class="sbt-setting-row">
          <n-text class="sbt-control-label">Size</n-text>
          <n-select
            v-model:value="imageSize"
            size="small"
            class="sbt-size-select"
            :options="IMAGE_SIZE_SELECT_OPTIONS"
            :consistent-menu-width="false"
          />
        </div>

        <div class="sbt-setting-block">
          <n-text class="sbt-control-label">Image Types</n-text>
          <n-checkbox-group
            v-model:value="selectedPatchImageTypes"
            class="sbt-image-type-group"
          >
            <n-checkbox
              v-for="option in PATCH_IMAGE_TYPE_OPTIONS"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </n-checkbox>
          </n-checkbox-group>
        </div>

        <div v-if="mode === 'review' && reviewImageOptions.length > 0" class="sbt-setting-row">
          <n-text class="sbt-control-label">Review Images</n-text>
          <n-select
            v-model:value="selectedReviewImageIndexes"
            multiple
            size="small"
            class="sbt-review-image-select"
            :options="reviewImageOptions"
            :consistent-menu-width="false"
            placeholder="Review"
          />
        </div>
      </div>
    </n-modal>

    <!-- Empty state -->
    <div v-if="visibleSamples.length === 0" class="sbt-empty">
      <n-text depth="3">
        {{ mode === "review" ? "No samples with review images" : "No rows to display" }}
      </n-text>
    </div>

    <!-- Scroll body -->
    <div
      v-else
      class="sbt-scroll-shell"
      data-testid="blink-table-scrollbar"
    >
      <div
        ref="scrollRef"
        class="sbt-scroll"
        @scroll="handleScroll"
        @mousedown="onMouseDown"
      >
        <div class="sbt-vrow" :style="{ height: virtualizer.getTotalSize() + 'px', position: 'relative' }">
          <div class="sbt-rubber-band" :style="rubberBandStyle"></div>
          <div
            v-for="virtualRow in virtualizer.getVirtualItems()"
            :key="virtualRow.index"
            class="sbt-row-wrapper"
            :class="{ 'sbt-vrow--odd': virtualRow.index % 2 === 1 }"
            :style="{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: virtualRowHeightStr,
              transform: `translateY(${virtualRow.start}px)`,
            }"
          >
            <div class="sbt-row" :style="{ minWidth: rowMinWidthStr }">
              <div
                v-for="sample in samplesForVirtualRow(virtualRow.index)"
                :key="sample.defectId"
                class="sbt-sample-block"
                :class="{ 'sbt-sample-block--selected': isSelected(sample.defectId) }"
                :data-defect-id="sample.defectId"
                :style="{ width: sampleBlockWidthStr(sample) }"
                @click.stop="handleSampleClick(sample, $event)"
              >
                <!-- Mini Header -->
                <div class="sbt-sample-mini-header">
                  <div v-if="blinkEnabled" class="sbt-sample-header-label">Blink</div>
                  <div
                    v-for="col in basePatchColumns"
                    :key="'base_header_' + col.spriteIndex"
                    class="sbt-sample-header-label"
                  >
                    {{ col.label }}
                  </div>
                  <template v-if="mode === 'review'">
                    <div
                      v-for="n in reviewColumnsForSample(sample)"
                      :key="'rev_header_' + n"
                      class="sbt-sample-header-label"
                    >
                      Rev {{ n + 1 }}
                    </div>
                  </template>
                </div>

                <!-- Images Row -->
                <div class="sbt-sample-images-row" :style="{ height: imageCellHeightPxStr }">
                  <!-- Blink Cell -->
                  <div v-if="blinkEnabled" class="sbt-img-cell">
                    <template v-if="shouldRenderSprite(sample)">
                      <!-- Base reference layer -->
                      <div class="sbt-sprite-layer" :style="getSpriteStyle(sample, blinkBaseSpriteIndex())"></div>
                      <!-- Defective overlay layer -->
                      <div
                        class="sbt-sprite-layer sbt-overlay"
                        :class="{ 'is-active': blinkPhase === 'B' }"
                        :style="getSpriteStyle(sample, blinkOverlaySpriteIndex())"
                      ></div>
                    </template>
                    <div v-else class="sbt-img-placeholder"></div>
                    <div class="sbt-defect-id">{{ sample.defectId }}</div>
                  </div>

                  <!-- Base patch cells -->
                  <div v-for="col in basePatchColumns" :key="'base_' + col.spriteIndex" class="sbt-img-cell">
                    <div v-if="shouldRenderSprite(sample)" class="sbt-sprite-layer" :style="getSpriteStyle(sample, col.spriteIndex)"></div>
                    <div v-else class="sbt-img-placeholder"></div>
                  </div>

                  <!-- Review Cells -->
                  <template v-if="mode === 'review'">
                    <div
                      v-for="n in reviewColumnsForSample(sample)"
                      :key="'rev_' + n"
                      class="sbt-img-cell"
                    >
                      <div v-if="shouldRenderSprite(sample)" class="sbt-sprite-layer" :style="getSpriteStyle(sample, patchImageTypesForSprite.length + n)"></div>
                      <div v-else class="sbt-img-placeholder"></div>
                    </div>
                  </template>
                </div>

                <!-- Prediction / Annotation / Draft Badges -->
                <div v-if="showPredictionBadges" class="sbt-prediction-row">
                  <n-tag
                    v-if="annotationDrafts[defectIdKey(sample.defectId)]"
                    type="warning"
                    size="small"
                    class="sbt-prediction-badge"
                    title="Draft (unsubmitted)"
                  >
                    D: {{ annotationDrafts[defectIdKey(sample.defectId)] }}
                  </n-tag>
                  <n-tag
                    v-if="annotationLabels[defectIdKey(sample.defectId)]"
                    type="success"
                    size="small"
                    class="sbt-prediction-badge"
                    title="Annotation (saved)"
                  >
                    A: {{ annotationLabels[defectIdKey(sample.defectId)] }}
                  </n-tag>
                  <n-tag
                    v-if="predictionLabels[defectIdKey(sample.defectId)]"
                    type="info"
                    size="small"
                    class="sbt-prediction-badge"
                    title="Latest prediction"
                  >
                    P: {{ predictionLabels[defectIdKey(sample.defectId)] }}{{ predictionConfidences[defectIdKey(sample.defectId)] != null ? ` (${(predictionConfidences[defectIdKey(sample.defectId)]! * 100).toFixed(0)}%)` : '' }}
                  </n-tag>
                  <div v-else></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div
        v-if="showYScrollbar"
        class="sbt-scrollbar-rail sbt-scrollbar-rail--y"
        @mousedown.prevent="jumpScrollbar('y', $event)"
      >
        <div
          class="sbt-scrollbar-thumb"
          :style="yThumbStyle"
          @mousedown.stop.prevent="beginScrollbarDrag('y', $event)"
        ></div>
      </div>
      <div
        v-if="showXScrollbar"
        class="sbt-scrollbar-rail sbt-scrollbar-rail--x"
        @mousedown.prevent="jumpScrollbar('x', $event)"
      >
        <div
          class="sbt-scrollbar-thumb"
          :style="xThumbStyle"
          @mousedown.stop.prevent="beginScrollbarDrag('x', $event)"
        ></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sbt {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  background: var(--cv-card-bg, #1e1e2e);
  border: 1px solid var(--cv-border, rgba(255, 255, 255, 0.12));
  border-radius: 8px;
  overflow: hidden;
}

/* Toolbar */
.sbt-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--cv-border, rgba(255, 255, 255, 0.12));
  background: color-mix(
    in srgb,
    var(--cv-card-bg, #1e1e2e) 50%,
    var(--cv-bg, #16162a)
  );
  flex-shrink: 0;
}

.sbt-toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.sbt-toolbar-right {
  display: flex;
  align-items: center;
}

.sbt-blink-label {
  font-size: 13px;
  font-weight: 500;
}

.sbt-row-count {
  font-size: 12px;
}

.sbt-mode-radio {
  margin-left: 6px;
}

.sbt-per-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.sbt-per-row-label {
  font-size: 11px;
  white-space: nowrap;
}

.sbt-per-row-button {
  width: 22px;
  min-width: 22px;
  padding: 0;
}

.sbt-per-row-value {
  width: 14px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  text-align: center;
}

.sbt-review-status {
  font-size: 12px;
}

.sbt-control {
  display: flex;
  align-items: center;
  gap: 4px;
}

.sbt-control-label {
  font-size: 11px;
  white-space: nowrap;
}

.sbt-size-select {
  width: 72px;
}

.sbt-review-image-select {
  width: 150px;
}

.sbt-settings {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.sbt-setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.sbt-setting-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sbt-image-type-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* Scroll body */
.sbt-scroll-shell {
  flex: 1;
  min-height: 0;
  position: relative;
  user-select: none;
  overflow: hidden;
}

.sbt-scroll {
  width: 100%;
  height: 100%;
  overflow: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.sbt-scroll::-webkit-scrollbar {
  width: 0;
  height: 0;
}

.sbt-scrollbar-rail {
  position: absolute;
  z-index: 20;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.28);
  user-select: none;
}

.sbt-scrollbar-rail--y {
  top: 0;
  right: 0;
  bottom: 0;
  width: 10px;
}

.sbt-scrollbar-rail--x {
  right: 0;
  bottom: 0;
  left: 0;
  height: 10px;
}

.sbt-scrollbar-thumb {
  width: 100%;
  height: 100%;
  border-radius: 999px;
  background: rgba(142, 160, 255, 0.7);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.16);
  cursor: pointer;
}

.sbt-scrollbar-thumb:hover {
  background: rgba(142, 160, 255, 0.9);
}

/* Virtual row wrapper */
.sbt-vrow {
  box-sizing: border-box;
}

.sbt-vrow--odd .sbt-row {
  background: color-mix(
    in srgb,
    var(--cv-card-bg, #1e1e2e) 60%,
    var(--cv-bg, #16162a)
  );
}

/* Row (horizontal flex of sample blocks) */
.sbt-row {
  display: flex;
  align-items: stretch;
  padding: v-bind("ROW_PADDING_Y + 'px'") 12px;
  gap: 12px;
  height: 100%;
  box-sizing: border-box;
}

/* Sample block */
.sbt-sample-block {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 0 0 auto;
  border-radius: 4px;
  padding: 2px;
  box-sizing: border-box;
  transition: background-color 0.15s, box-shadow 0.15s;
}

.sbt-sample-block--selected {
  background: color-mix(
    in srgb,
    var(--cv-primary, #4098fc) 12%,
    transparent
  );
  box-shadow: inset 0 0 0 2px var(--cv-primary, #4098fc);
}

/* Mini-header */
.sbt-sample-mini-header {
  display: flex;
  gap: 4px;
  height: v-bind("MINI_HEADER_HEIGHT + 'px'");
  align-items: center;
  padding: 0 2px;
}

.sbt-sample-header-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.5));
  text-transform: uppercase;
  letter-spacing: 0.3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: center;
  flex-shrink: 0;
  width: v-bind("cellSizePx");
}

/* Images row */
.sbt-sample-images-row {
  display: flex;
  gap: 4px;
  box-sizing: border-box;
}

/* Image cell — fixed square, preserve 1:1 aspect ratio */
.sbt-img-cell {
  position: relative;
  width: v-bind("cellSizePx");
  height: v-bind("cellSizePx");
  overflow: hidden;
  background: #111;
  flex-shrink: 0;
}

.sbt-sprite-layer {
  width: 100%;
  height: 100%;
}

.sbt-img-placeholder {
  width: 100%;
  height: 100%;
  background: rgba(255, 255, 255, 0.04);
}

/* Rubber band selection overlay */
.sbt-rubber-band {
  position: absolute;
  border: 2px dashed var(--cv-primary, #4098fc);
  background: color-mix(
    in srgb,
    var(--cv-primary, #4098fc) 15%,
    transparent
  );
  pointer-events: none;
  z-index: 10;
}

/* Empty state */
.sbt-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 200px;
}

/* Overlay toggle */
.sbt-overlay {
  position: absolute;
  top: 0;
  left: 0;
  opacity: 0;
}

.sbt-overlay.is-active {
  opacity: 1;
}

/* Defect ID label */
.sbt-defect-id {
  position: absolute;
  bottom: 2px;
  left: 2px;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.7);
  background: rgba(0, 0, 0, 0.55);
  padding: 1px 4px;
  border-radius: 2px;
  line-height: 1.2;
  max-width: calc(100% - 4px);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  pointer-events: none;
}

/* Prediction / Annotation / Draft badge row */
.sbt-prediction-row {
  height: 26px;
  padding: 2px;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 4px;
  box-sizing: border-box;
  overflow: hidden;
}

.sbt-prediction-badge {
  font-size: 10px;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
