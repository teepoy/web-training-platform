<script setup lang="ts">
import { computed } from "vue";
import { NButton, NIcon, NModal, NTag, NText } from "naive-ui";
import { FunnelOutline } from "@vicons/ionicons5";
import type { ScSampleTableFilter } from "@/features/sc/domain/sampleTable";
import ScGlobalFilterBar from "./ScGlobalFilterBar.vue";

const props = withDefaults(
  defineProps<{
    show: boolean;
    filter: ScSampleTableFilter;
    distinctValues: Record<string, Array<string | number>>;
    numericRanges?: Record<string, { min: number; max: number } | null>;
    numericRangeLoading?: Record<string, boolean>;
    numericRangeErrors?: Record<string, boolean>;
    showReclassifyColumns?: boolean;
  }>(),
  {
    numericRanges: () => ({}),
    numericRangeLoading: () => ({}),
    numericRangeErrors: () => ({}),
  },
);

const emit = defineEmits<{
  (e: "update:show", show: boolean): void;
  (e: "update:filter", filter: ScSampleTableFilter): void;
  (e: "search-options", payload: { field: string; search: string }): void;
  (e: "request-range", field: string): void;
}>();

const showModel = computed({
  get: () => props.show,
  set: (show: boolean) => emit("update:show", show),
});
const activeCount = computed(() => Object.keys(props.filter ?? {}).length);
</script>

<template>
  <NModal
    v-model:show="showModel"
    preset="card"
    class="sc-global-filter-modal"
    :bordered="false"
    :style="{ width: 'min(760px, calc(100vw - 32px))' }"
  >
    <template #header>
      <div class="sc-global-filter-header">
        <div class="sc-global-filter-icon" aria-hidden="true">
          <NIcon :size="18"><FunnelOutline /></NIcon>
        </div>
        <div class="sc-global-filter-heading">
          <div class="sc-global-filter-title-row">
            <span class="sc-global-filter-title">Global Filters</span>
            <NTag v-if="activeCount > 0" size="small" round type="success">
              {{ activeCount }} active
            </NTag>
          </div>
          <NText depth="3" class="sc-global-filter-description">
            {{
              showReclassifyColumns
                ? "Applied to map, table, gallery, sampling, and Train & Predict."
                : "Applied to map, table, and gallery."
            }}
          </NText>
        </div>
      </div>
    </template>

    <ScGlobalFilterBar
      class="sc-global-filter-editor"
      :filter="filter"
      :distinct-values="distinctValues"
      :numeric-ranges="numericRanges"
      :numeric-range-loading="numericRangeLoading"
      :numeric-range-errors="numericRangeErrors"
      :show-reclassify-columns="showReclassifyColumns"
      @update:filter="emit('update:filter', $event)"
      @search-options="emit('search-options', $event)"
      @request-range="emit('request-range', $event)"
    />

    <template #footer>
      <div class="sc-global-filter-footer">
        <NText depth="3" class="sc-global-filter-status">
          {{
            activeCount === 0
              ? "No filters applied"
              : activeCount === 1
                ? "1 filter field applied"
                : `${activeCount} filter fields applied`
          }}
        </NText>
        <NButton type="primary" size="small" @click="showModel = false">Done</NButton>
      </div>
    </template>
  </NModal>
</template>

<style scoped>
.sc-global-filter-modal {
  max-height: min(720px, calc(100vh - 32px));
}

.sc-global-filter-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.sc-global-filter-icon {
  display: grid;
  flex: 0 0 34px;
  width: 34px;
  height: 34px;
  place-items: center;
  color: var(--cv-primary, #4c80f0);
  border: 1px solid color-mix(in srgb, var(--cv-primary, #4c80f0) 24%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--cv-primary, #4c80f0) 9%, transparent);
}

.sc-global-filter-heading {
  min-width: 0;
}

.sc-global-filter-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 22px;
}

.sc-global-filter-title {
  font-size: 17px;
  font-weight: 600;
  line-height: 22px;
}

.sc-global-filter-description {
  display: block;
  margin-top: 3px;
  font-size: 12px;
  line-height: 18px;
}

.sc-global-filter-editor {
  margin: -4px 0;
}

.sc-global-filter-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.sc-global-filter-status {
  font-size: 12px;
}
</style>
