<script setup lang="ts">
import { ref, computed, watch, toRef } from "vue";
import {
  NSwitch,
  NText,
  NRadioGroup,
  NRadioButton,
  NButton,
  NTag,
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
    modifiers: { shift: boolean; ctrl: boolean; meta: boolean }
  ];
}>();

const mode = ref<"patch" | "review">("patch");
const MAX_SAMPLES_PER_ROW = 6;
const clampSamplesPerRow = (value: number): number =>
  Math.min(MAX_SAMPLES_PER_ROW, Math.max(1, value));
const patchPerRow = ref(clampSamplesPerRow(props.patchSamplesPerRow));
const reviewPerRow = ref(clampSamplesPerRow(props.reviewSamplesPerRow));
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
watch(reviewDisabled, (disabled) => {
  if (disabled && mode.value === "review") mode.value = "patch";
});

const samplesRef = computed(() =>
  mode.value === "review" ? props.reviewSamples ?? [] : props.samples,
);
const patchCellSizeRef = toRef(props, "patchCellSize");
const reviewCellSizeRef = toRef(props, "reviewCellSize");
const overscanRef = toRef(props, "overscan");
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

const cellSize = computed(() =>
  mode.value === "patch" ? props.patchCellSize : props.reviewCellSize
);

function reviewImageCount(sample: ScSampleItem): number {
  return Array.isArray(sample.reviewImages) ? sample.reviewImages.length : 0;
}

function reviewColumnsForSample(sample: ScSampleItem): number[] {
  return Array.from({ length: reviewImageCount(sample) }, (_, i) => i);
}

const maxReviewImageCount = computed(() => {
  if (mode.value !== "review") return 0;
  return visibleSamples.value.reduce(
    (max, sample) => Math.max(max, reviewImageCount(sample)),
    0,
  );
});

function cellsForSample(sample: ScSampleItem): number {
  const imageCells = mode.value === "patch" ? 3 : 3 + reviewImageCount(sample);
  return imageCells + (blinkEnabled.value ? 1 : 0);
}

const maxCellsPerSample = computed(() =>
  mode.value === "patch"
    ? 3 + (blinkEnabled.value ? 1 : 0)
    : 3 + maxReviewImageCount.value + (blinkEnabled.value ? 1 : 0),
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

const { enabled: blinkEnabled, phase: blinkPhase, toggle: toggleBlink } = useBlinkController({
  intervalMs: props.blinkIntervalMs,
  initialEnabled: props.initialBlinkEnabled,
});

const requestedSpriteUrls = ref<Set<string>>(new Set());

function isSelected(defectId: number | string): boolean {
  const idStr = defectId.toString();
  if (props.selectedDefectIds instanceof Set) {
    return props.selectedDefectIds.has(idStr);
  }
  return props.selectedDefectIds.includes(idStr);
}

function getSpriteUrl(sample: ScSampleItem): string {
  const isPatch = mode.value === "patch";
  const cs = isPatch ? props.patchCellSize : props.reviewCellSize;
  const t = props.inspectionTime ?? String(sample.inspectionTime);
  return isPatch
    ? `/api/v1/sc/sprites/patch/${t}/${sample.waferKey}/${sample.defectId}?cell_size=${cs}`
    : `/api/v1/sc/sprites/review/${t}/${sample.waferKey}/${sample.defectId}?review_count=${reviewImageCount(sample)}&cell_size=${cs}`;
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
  const cols = isPatch ? 3 : 3 + reviewImageCount(sample);
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

function handleScroll() {
  queueViewportImageLoad();
}

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

        <div class="sbt-per-row">
          <n-text class="sbt-per-row-label">PerRow:</n-text>
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
      <div class="sbt-toolbar-right">
        <n-text class="sbt-row-count" depth="3">
          {{ visibleSamples.length }} samples
        </n-text>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="visibleSamples.length === 0" class="sbt-empty">
      <n-text depth="3">
        {{ mode === "review" ? "No samples with review images" : "No rows to display" }}
      </n-text>
    </div>

    <!-- Scroll body -->
    <div
      v-else
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
            >
              <!-- Mini Header -->
              <div class="sbt-sample-mini-header">
                <div v-if="blinkEnabled" class="sbt-sample-header-label">Blink</div>
                <div class="sbt-sample-header-label">Template</div>
                <div class="sbt-sample-header-label">Defective</div>
                <div class="sbt-sample-header-label">Difference</div>
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
                    <!-- Base Template layer -->
                    <div class="sbt-sprite-layer" :style="getSpriteStyle(sample, 0)"></div>
                    <!-- Defective Overlay layer -->
                    <div
                      class="sbt-sprite-layer sbt-overlay"
                      :class="{ 'is-active': blinkPhase === 'B' }"
                      :style="getSpriteStyle(sample, 1)"
                    ></div>
                  </template>
                  <div v-else class="sbt-img-placeholder"></div>
                  <div class="sbt-defect-id">{{ sample.defectId }}</div>
                </div>

                <!-- Template, Defective, Difference Cells -->
                <div v-for="col in [0, 1, 2]" :key="'base_' + col" class="sbt-img-cell">
                  <div v-if="shouldRenderSprite(sample)" class="sbt-sprite-layer" :style="getSpriteStyle(sample, col)"></div>
                  <div v-else class="sbt-img-placeholder"></div>
                </div>

                <!-- Review Cells -->
                <template v-if="mode === 'review'">
                  <div
                    v-for="n in reviewColumnsForSample(sample)"
                    :key="'rev_' + n"
                    class="sbt-img-cell"
                  >
                    <div v-if="shouldRenderSprite(sample)" class="sbt-sprite-layer" :style="getSpriteStyle(sample, 3 + n)"></div>
                    <div v-else class="sbt-img-placeholder"></div>
                  </div>
                </template>
              </div>

              <!-- Prediction / Annotation / Draft Badges -->
              <div v-if="showPredictionBadges" class="sbt-prediction-row">
                <n-tag
                  v-if="annotationDrafts[sample.defectId]"
                  type="warning"
                  size="small"
                  class="sbt-prediction-badge"
                  title="Draft (unsubmitted)"
                >
                  D: {{ annotationDrafts[sample.defectId] }}
                </n-tag>
                <n-tag
                  v-if="annotationLabels[sample.defectId]"
                  type="success"
                  size="small"
                  class="sbt-prediction-badge"
                  title="Annotation (saved)"
                >
                  A: {{ annotationLabels[sample.defectId] }}
                </n-tag>
                <n-tag
                  v-if="predictionLabels[sample.defectId]"
                  type="info"
                  size="small"
                  class="sbt-prediction-badge"
                  title="Latest prediction"
                >
                  P: {{ predictionLabels[sample.defectId] }}{{ predictionConfidences[sample.defectId] != null ? ` (${(predictionConfidences[sample.defectId]! * 100).toFixed(0)}%)` : '' }}
                </n-tag>
                <div v-else></div>
              </div>
            </div>
          </div>
        </div>
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
  margin-left: 4px;
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

/* Scroll body */
.sbt-scroll {
  flex: 1;
  overflow-y: auto;
  overflow-x: auto;
  position: relative;
  user-select: none;
}

.sbt-scroll::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.sbt-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.sbt-scroll::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
}

.sbt-scroll::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.2);
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
