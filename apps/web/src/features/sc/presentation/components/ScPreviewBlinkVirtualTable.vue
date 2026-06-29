<script setup lang="ts">
import { nextTick, onBeforeUnmount, onBeforeUpdate, onUpdated, ref, watch, watchEffect } from "vue";
import { NSpin } from "naive-ui";
import type { ScSampleItem } from "@/features/sc/generated/proto/sc/v1/sample_pb";
import BlinkVirtualTableWithSelectionAndPreviewResultDisplay from "@/shared/components/blink-virtual-table/BlinkVirtualTableWithSelectionAndPreviewResultDisplay.vue";

const props = withDefaults(
  defineProps<{
    samples?: ScSampleItem[];
    reviewSamples?: ScSampleItem[];
    reviewLoading?: boolean;
    reviewError?: string | null;
    /** @deprecated Image URLs are now resolved by sprite endpoints. */
    imageUrlsByDefectId?: Record<string, any>;
    selectedDefectIds?: Set<string> | string[];
    patchSamplesPerRow?: number;
    reviewSamplesPerRow?: number;
    overscan?: number;
    inspectionTime?: string;
    hasNextPage?: boolean;
    isFetchingNextPage?: boolean;
    onLoadMore?: () => void;
    total?: number;
  }>(),
  {
    samples: () => [],
    reviewSamples: () => [],
    patchSamplesPerRow: 4,
    reviewSamplesPerRow: 1,
    overscan: 10,
    hasNextPage: false,
    isFetchingNextPage: false,
  },
);

const emit = defineEmits<{
  selectSamples: [
    defectIds: string[],
    modifiers: {
      shift: boolean;
      ctrl: boolean;
      meta: boolean;
      selectionMode?: "replace" | "add" | "toggle";
    },
  ];
  modeChange: [mode: "patch" | "review"];
}>();

const sentinelRef = ref<HTMLElement | null>(null);
const scrollContainer = ref<HTMLElement | null>(null);

let observer: IntersectionObserver | null = null;
let lastIntersecting = false;

function selectionLog(step: string, detail: Record<string, unknown> = {}): void {
  console.log(
    "[sc-selection]",
    new Date().toISOString(),
    `${performance.now().toFixed(1)}ms`,
    step,
    detail,
  );
}

let previewRenderStart = 0;
onBeforeUpdate(() => {
  previewRenderStart = performance.now();
  selectionLog("preview blink beforeUpdate", {
    samples: props.samples.length,
    selected:
      props.selectedDefectIds instanceof Set
        ? props.selectedDefectIds.size
        : (props.selectedDefectIds?.length ?? 0),
  });
});
onUpdated(() => {
  const updatedAt = performance.now();
  selectionLog("preview blink updated", {
    ms: Number((updatedAt - previewRenderStart).toFixed(2)),
    samples: props.samples.length,
  });
  void nextTick(() => {
    selectionLog("preview blink nextTick", {
      ms: Number((performance.now() - updatedAt).toFixed(2)),
    });
  });
});

function maybeLoadMore(): void {
  if (props.hasNextPage && !props.isFetchingNextPage) props.onLoadMore?.();
}

function setupIntersectionObserver(): void {
  observer?.disconnect();
  const root = scrollContainer.value;
  if (!root || !sentinelRef.value || typeof IntersectionObserver === "undefined") return;
  observer = new IntersectionObserver(
    (entries) => {
      const isIntersecting = entries[0]?.isIntersecting === true;
      if (isIntersecting && !lastIntersecting) maybeLoadMore();
      lastIntersecting = isIntersecting;
    },
    { root, rootMargin: "200px" },
  );
  observer.observe(sentinelRef.value);
}

function handleScrollContainerChange(element: HTMLElement | null): void {
  scrollContainer.value = element;
}

watchEffect(() => {
  if (scrollContainer.value && sentinelRef.value) setupIntersectionObserver();
});

watch(
  () => props.samples,
  (samples) => {
    selectionLog("preview blink samples prop", { rows: samples?.length ?? 0 });
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  observer?.disconnect();
});
</script>

<template>
  <div class="sc-preview-table-wrapper">
    <BlinkVirtualTableWithSelectionAndPreviewResultDisplay
      class="sc-preview-table"
      :samples="props.samples"
      :review-samples="props.reviewSamples"
      :review-loading="props.reviewLoading"
      :review-error="props.reviewError"
      :patch-samples-per-row="props.patchSamplesPerRow"
      :review-samples-per-row="props.reviewSamplesPerRow"
      :selected-defect-ids="props.selectedDefectIds"
      :show-prediction-badges="false"
      :show-mode-switch="true"
      :overscan="props.overscan"
      :inspection-time="props.inspectionTime"
      :total="props.total"
      @select-samples="(ids, mods) => emit('selectSamples', ids, mods)"
      @scroll-container-change="handleScrollContainerChange"
      @mode-change="emit('modeChange', $event)"
      @near-bottom="maybeLoadMore"
    />
    <Teleport v-if="scrollContainer" :to="scrollContainer">
      <div
        ref="sentinelRef"
        class="sc-preview-sentinel"
        data-testid="preview-table-loadmore-sentinel"
      >
        <NSpin v-if="props.isFetchingNextPage" size="small" />
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.sc-preview-table-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.sc-preview-table {
  flex: 1;
  min-height: 0;
}

.sc-preview-sentinel {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 32px;
  padding: 8px;
}
</style>
