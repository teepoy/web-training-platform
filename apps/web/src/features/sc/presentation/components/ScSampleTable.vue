<script setup lang="ts">
import { ref } from "vue";
import type { ScSampleTableDataSource } from "@/features/sc/domain/workbenchInteraction";
import type { ScSampleTableBaseProps, ScSampleTableEmits } from "./scSampleTableContract";
import ScSampleTableTanStack from "./ScSampleTableTanStack.vue";

interface ScSampleTableRendererProps extends ScSampleTableBaseProps {
  dataSource: ScSampleTableDataSource;
  defectIds?: string[];
  pageSize?: number;
}

interface ScSampleTableExpose {
  getDefectCoords(defectId: number):
    | {
        waferX: number;
        waferY: number;
        dieX: number;
        dieY: number;
        reticleX: number;
        reticleY: number;
      }
    | undefined;
}

defineProps<ScSampleTableRendererProps>();
defineEmits<ScSampleTableEmits>();

const rendererRef = ref<ScSampleTableExpose | null>(null);

defineExpose({
  getDefectCoords(defectId: number) {
    return rendererRef.value?.getDefectCoords(defectId);
  },
});
</script>

<template>
  <ScSampleTableTanStack
    ref="rendererRef"
    :data-source="dataSource"
    :defect-ids="defectIds"
    :page-size="pageSize"
    :loading="loading"
    :selection="selection"
    :filter="filter"
    :sort="sort"
    :show-reclassify-columns="showReclassifyColumns"
    :enable-selection="enableSelection"
    @selection-change="$emit('selection-change', $event)"
    @filter-change="$emit('filter-change', $event)"
    @sort-change="$emit('sort-change', $event)"
  />
</template>
