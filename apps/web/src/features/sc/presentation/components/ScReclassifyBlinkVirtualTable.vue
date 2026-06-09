<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watchEffect, nextTick } from "vue";
import { NSpin } from "naive-ui";
import type { ScSampleItem } from "@/features/sc/generated/proto/sc/v1/sample_pb";
import { BlinkVirtualTableWithSelectionAndPreviewResultDisplay } from "@/shared/components/blink-virtual-table";

const props = withDefaults(
  defineProps<{
    samples: ScSampleItem[];
    imageUrlsByDefectId?: Record<string, any>;
    selectedDefectIds?: Set<string> | string[];
    predictionLabels?: Record<string, string>;
    predictionConfidences?: Record<string, number | null>;
    annotationLabels?: Record<string, string>;
    annotationDrafts?: Record<string, string>;
    reviewCount?: number;
    patchSamplesPerRow?: number;
    reviewSamplesPerRow?: number;
    overscan?: number;
    hasNextPage?: boolean;
    isFetchingNextPage?: boolean;
    onLoadMore?: () => void;
  }>(),
  {
    reviewCount: 3,
    patchSamplesPerRow: 5,
    reviewSamplesPerRow: 1,
    predictionLabels: () => ({}),
    predictionConfidences: () => ({}),
    annotationLabels: () => ({}),
    annotationDrafts: () => ({}),
    overscan: 10,
    hasNextPage: false,
    isFetchingNextPage: false,
  }
);

const emit = defineEmits<{
  selectSamples: [
    defectIds: string[],
    modifiers: { shift: boolean; ctrl: boolean; meta: boolean },
  ];
}>();

const blinkTableRef = ref<InstanceType<typeof BlinkVirtualTableWithSelectionAndPreviewResultDisplay> | null>(null);
const sentinelRef = ref<HTMLElement | null>(null);

let observer: IntersectionObserver | null = null;
let lastIntersecting = false;

function getScrollContainer(): HTMLElement | null {
  return blinkTableRef.value?.scrollRef ?? null;
}

function setupIntersectionObserver() {
  if (observer) observer.disconnect();

  const root = getScrollContainer();
  if (!root) return;

  observer = new IntersectionObserver(
    (entries) => {
      const entry = entries[0];
      const isIntersecting = entry.isIntersecting;

      if (isIntersecting && !lastIntersecting) {
        if (props.hasNextPage && !props.isFetchingNextPage) {
          props.onLoadMore?.();
        }
      }
      lastIntersecting = isIntersecting;
    },
    { root, rootMargin: '200px' }
  );

  if (sentinelRef.value) {
    observer.observe(sentinelRef.value);
  }
}

onMounted(() => {
  nextTick(() => {
    setupIntersectionObserver();
  });
});

watchEffect((onCleanup) => {
  if (sentinelRef.value && observer) {
    observer.observe(sentinelRef.value);
    onCleanup(() => {
      if (sentinelRef.value && observer) {
        observer.unobserve(sentinelRef.value);
      }
    });
  }
});

onBeforeUnmount(() => {
  if (observer) observer.disconnect();
});
</script>

<template>
  <div class="sc-reclassify-table-wrapper">
    <BlinkVirtualTableWithSelectionAndPreviewResultDisplay
      ref="blinkTableRef"
      class="sc-reclassify-table"
      :samples="samples"
      :patch-samples-per-row="patchSamplesPerRow"
      :review-samples-per-row="reviewSamplesPerRow"
      :review-count="reviewCount"
      :selected-defect-ids="selectedDefectIds"
      :prediction-labels="predictionLabels"
      :prediction-confidences="predictionConfidences"
      :annotation-labels="annotationLabels"
      :annotation-drafts="annotationDrafts"
      :show-prediction-badges="true"
      :show-mode-switch="true"
      :overscan="overscan"
      @select-samples="(ids, mods) => emit('selectSamples', ids, mods)"
    />
    <Teleport v-if="getScrollContainer()" :to="getScrollContainer()!">
      <div
        ref="sentinelRef"
        class="sc-reclassify-sentinel"
        data-testid="reclassify-table-loadmore-sentinel"
      >
        <NSpin
          v-if="isFetchingNextPage"
          size="small"
          data-testid="reclassify-table-loadmore-spinner"
        />
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.sc-reclassify-table-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.sc-reclassify-table {
  flex: 1;
  min-height: 0;
}
.sc-reclassify-sentinel {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px;
  min-height: 32px;
}
</style>
