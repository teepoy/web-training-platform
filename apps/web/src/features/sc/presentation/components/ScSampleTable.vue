<script setup lang="ts">
import { defineAsyncComponent, ref } from "vue";
import type { ScSampleTableDataSource } from "@/features/sc/domain/workbenchInteraction";
import { resolveScSampleTableImplementation } from "./sampleTableImplementation";
import type { ScSampleTableBaseProps, ScSampleTableEmits } from "./scSampleTableContract";

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
const implementation = resolveScSampleTableImplementation(
  typeof window === "undefined" ? "" : window.location.search,
  import.meta.env.DEV,
);
// This is a migration A/B boundary, not a second public table contract. Keep
// renderer-specific behavior behind this component and remove the losing
// implementation after the comparison. Loading only the selected renderer
// also keeps TanStack out of the production workbench bundle while VXE is the
// default.
const renderer = defineAsyncComponent(() =>
  implementation === "tanstack"
    ? import("./ScSampleTableTanStack.vue")
    : import("./ScSampleTableVxe.vue"),
);

defineExpose({
  getDefectCoords(defectId: number) {
    return rendererRef.value?.getDefectCoords(defectId);
  },
});
</script>

<template>
  <component
    :is="renderer"
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
    :data-sample-table-implementation="implementation"
    @selection-change="$emit('selection-change', $event)"
    @filter-change="$emit('filter-change', $event)"
    @sort-change="$emit('sort-change', $event)"
  />
</template>
