<script setup lang="ts">
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
  }>(),
  {
    samples: () => [],
    reviewSamples: () => [],
    patchSamplesPerRow: 4,
    reviewSamplesPerRow: 1,
    overscan: 10,
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
}>();
</script>

<template>
  <BlinkVirtualTableWithSelectionAndPreviewResultDisplay
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
    @select-samples="(ids, mods) => emit('selectSamples', ids, mods)"
  />
</template>
