import { ref, computed, nextTick, watch, onBeforeUnmount, type Ref } from "vue";
import { useVirtualizer } from "@tanstack/vue-virtual";
import type { ScSampleItem } from "@/features/sc/generated/proto/sc/v1/sample_pb";

export const IMAGE_LOAD_DEBOUNCE_MS = 180;
export const MINI_HEADER_HEIGHT = 20;
export const HEADER_IMAGE_GAP = 4;
export const ROW_PADDING_Y = 2;

export interface UseBlinkVirtualScrollParams {
  samples: Ref<ScSampleItem[]>;
  mode: Ref<"patch" | "review">;
  patchPerRow: Ref<number>;
  reviewPerRow: Ref<number>;
  patchCellSize?: Ref<number>;
  reviewCellSize?: Ref<number>;
  extraRowHeight?: Ref<number>;
  overscan?: Ref<number>;
}

export function useBlinkVirtualScroll(params: UseBlinkVirtualScrollParams) {
  const { samples, mode, patchPerRow, reviewPerRow } = params;
  const patchCellSize = params.patchCellSize;
  const reviewCellSize = params.reviewCellSize;
  const extraRowHeight = params.extraRowHeight;
  const overscan = params.overscan;

  const effectiveSamplesPerRow = computed(() =>
    mode.value === "patch" ? patchPerRow.value : reviewPerRow.value,
  );

  const visibleSamples = computed<ScSampleItem[]>(() => {
    if (mode.value === "review") {
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

  const virtualRowCount = computed(() =>
    Math.ceil(Math.max(visibleSamples.value.length, 1) / effectiveSamplesPerRow.value),
  );

  function samplesForVirtualRow(rowIdx: number): ScSampleItem[] {
    const perRow = effectiveSamplesPerRow.value;
    const start = rowIdx * perRow;
    return visibleSamples.value.slice(start, start + perRow);
  }

  const scrollRef = ref<HTMLElement | null>(null);
  const shouldLoadImages = ref(true);
  let imageLoadDebounceTimer: number | undefined;

  const virtualizer = useVirtualizer({
    get count() {
      if (visibleSamples.value.length === 0) return 0;
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
    ],
    () => {
      void nextTick(() => virtualizer.value.measure());
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
    maxReviewImages,
    reviewColumnIndices,
    imageCellHeightPx,
    imageCellHeightPxStr,
    samplesForVirtualRow,
  };
}
