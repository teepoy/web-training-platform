<script setup lang="ts">
import { computed } from "vue";
import { NModal, NText } from "naive-ui";
import type { ScSampleTableFilter } from "@/features/sc/domain/sampleTable";
import ScGlobalFilterBar from "./ScGlobalFilterBar.vue";

const props = defineProps<{
  show: boolean;
  filter: ScSampleTableFilter;
  distinctValues: Record<string, Array<string | number>>;
  showReclassifyColumns?: boolean;
}>();

const emit = defineEmits<{
  (e: "update:show", show: boolean): void;
  (e: "update:filter", filter: ScSampleTableFilter): void;
  (e: "search-options", payload: { field: string; search: string }): void;
}>();

const showModel = computed({
  get: () => props.show,
  set: (show: boolean) => emit("update:show", show),
});
</script>

<template>
  <NModal
    v-model:show="showModel"
    preset="card"
    title="Global Filter"
    :style="{ width: 'min(960px, calc(100vw - 32px))' }"
  >
    <NText depth="3" class="sc-global-filter-description">
      {{
        showReclassifyColumns
          ? "Filters apply to the map, table, gallery, sampling, and Train & Predict."
          : "Filters apply to the map, table, and gallery."
      }}
    </NText>
    <ScGlobalFilterBar
      class="sc-global-filter-editor"
      :filter="filter"
      :distinct-values="distinctValues"
      :show-reclassify-columns="showReclassifyColumns"
      @update:filter="emit('update:filter', $event)"
      @search-options="emit('search-options', $event)"
    />
  </NModal>
</template>

<style scoped>
.sc-global-filter-description {
  display: block;
  margin-bottom: 14px;
  font-size: 12px;
}

.sc-global-filter-editor {
  padding: 0;
  border-bottom: 0;
}
</style>
