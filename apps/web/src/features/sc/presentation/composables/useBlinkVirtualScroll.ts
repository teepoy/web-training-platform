import { ref, computed, nextTick, watch, onBeforeUnmount, type Ref } from "vue";
import { useVirtualizer } from "@tanstack/vue-virtual";

export const IMAGE_LOAD_DEBOUNCE_MS = 180;
export const MINI_HEADER_HEIGHT = 20;
export const HEADER_IMAGE_GAP = 4;
export const ROW_PADDING_Y = 2;

export interface UseBlinkVirtualScrollParams<TSample extends { reviewImages: unknown[] }> {
  samples: Ref<TSample[]>;
  mode: Ref<"patch" | "review">;
  patchPerRow: Ref<number>;
  reviewPerRow: Ref<number>;
  totalSamples?: Ref<number | undefined>;
  sampleOffset?: Ref<number>;
  patchCellSize?: Ref<number>;
  reviewCellSize?: Ref<number>;
  extraRowHeight?: Ref<number>;
  overscan?: Ref<number>;
  reviewSamplesArePreFiltered?: boolean;
}

export function useBlinkVirtualScroll<TSample extends { reviewImages: unknown[] }>(
  params: UseBlinkVirtualScrollParams<TSample>,
) {
  const { samples, mode, patchPerRow, reviewPerRow } = params;
  const patchCellSize = params.patchCellSize;
  const reviewCellSize = params.reviewCellSize;
  const extraRowHeight = params.extraRowHeight;
  const overscan = params.overscan;
  const sampleOffset = params.sampleOffset;

  const effectiveSamplesPerRow = computed(() =>
    mode.value === "patch" ? patchPerRow.value : reviewPerRow.value,
  );

  const visibleSamples = computed<TSample[]>(() => {
    if (mode.value === "review" && params.reviewSamplesArePreFiltered !== true) {
      return samples.value.filter((s) => s.reviewImages.length > 0);
    }
    return samples.value;
  });

  const maxReviewImages = computed<number>(() => {
    if (mode.value !== "review") return 0;
    return visibleSamples.value.reduce((max, s) => Math.max(max, s.reviewImages.length), 0);
  });

  const reviewColumnIndices = computed<number[]>(() =>
    Array.from({ length: maxReviewImages.value }, (_, i) => i),
  );

  const rowHeight = computed(() => {
    if (mode.value === "patch") {
      return (patchCellSize?.value ?? 64) + 4;
    }
    return (reviewCellSize?.value ?? 128) + 4;
  });

  const imageCellHeightPx = computed(() => rowHeight.value - 4);

  const imageCellHeightPxStr = computed(() => `${imageCellHeightPx.value}px`);

  const virtualRowHeight = computed(
    () =>
      MINI_HEADER_HEIGHT +
      HEADER_IMAGE_GAP +
      imageCellHeightPx.value +
      ROW_PADDING_Y * 2 +
      (extraRowHeight?.value ?? 0),
  );

  const virtualRowHeightStr = computed(() => `${virtualRowHeight.value}px`);

  const virtualSampleCount = computed(() => {
    if (mode.value === "review" && params.reviewSamplesArePreFiltered !== true) {
      return visibleSamples.value.length;
    }
    return Math.max(
      params.totalSamples?.value ?? visibleSamples.value.length,
      visibleSamples.value.length,
    );
  });

  const virtualRowCount = computed(() =>
    Math.ceil(Math.max(virtualSampleCount.value, 1) / effectiveSamplesPerRow.value),
  );

  function samplesForVirtualRow(rowIdx: number): TSample[] {
    const perRow = effectiveSamplesPerRow.value;
    const globalStart = rowIdx * perRow;
    const usesPagedWindow = mode.value === "patch" || params.reviewSamplesArePreFiltered === true;
    const localStart = usesPagedWindow ? globalStart - (sampleOffset?.value ?? 0) : globalStart;
    return localStart >= 0 && localStart < visibleSamples.value.length
      ? visibleSamples.value.slice(localStart, localStart + perRow)
      : [];
  }

  const scrollRef = ref<HTMLElement | null>(null);
  const shouldLoadImages = ref(true);
  let imageLoadDebounceTimer: number | undefined;

  const virtualizer = useVirtualizer({
    get count() {
      if (virtualSampleCount.value === 0) return 0;
      return virtualRowCount.value;
    },
    getScrollElement: () => scrollRef.value,
    estimateSize: () => virtualRowHeight.value,
    get overscan() {
      return overscan?.value ?? 10;
    },
  });

  function queueViewportImageLoad(): void {
    shouldLoadImages.value = false;
    if (imageLoadDebounceTimer !== undefined) {
      window.clearTimeout(imageLoadDebounceTimer);
    }
    imageLoadDebounceTimer = window.setTimeout(() => {
      shouldLoadImages.value = true;
      imageLoadDebounceTimer = undefined;
    }, IMAGE_LOAD_DEBOUNCE_MS);
  }

  watch(
    [
      mode,
      patchPerRow,
      reviewPerRow,
      virtualRowHeight,
      effectiveSamplesPerRow,
      () => visibleSamples.value.length,
      () => virtualSampleCount.value,
      () => sampleOffset?.value ?? 0,
    ],
    () => {
      void nextTick(() => {
        virtualizer.value.measure();
      });
    },
    { flush: "post" },
  );

  onBeforeUnmount(() => {
    if (imageLoadDebounceTimer !== undefined) {
      window.clearTimeout(imageLoadDebounceTimer);
    }
  });

  return {
    virtualizer,
    virtualRowCount,
    virtualRowHeight,
    virtualRowHeightStr,
    effectiveSamplesPerRow,
    shouldLoadImages,
    queueViewportImageLoad,
    scrollRef,
    visibleSamples,
    virtualSampleCount,
    maxReviewImages,
    reviewColumnIndices,
    imageCellHeightPx,
    imageCellHeightPxStr,
    samplesForVirtualRow,
  };
}
