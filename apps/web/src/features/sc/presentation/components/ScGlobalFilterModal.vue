<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { NButton, NModal, NTag } from "naive-ui";
import {
  cloneScGlobalFilter,
  scGlobalFilterConditionCount,
  type ScGlobalFilter,
} from "@/features/sc/domain/globalFilter";
import type { ScDataColumn } from "@/features/sc/domain/workbenchDataSource";
import ScGlobalFilterBar from "./ScGlobalFilterBar.vue";

const props = withDefaults(
  defineProps<{
    show: boolean;
    filter: ScGlobalFilter;
    columns?: ScDataColumn[];
    distinctValues: Record<string, Array<string | number>>;
    numericRanges?: Record<string, { min: number; max: number } | null>;
    numericRangeLoading?: Record<string, boolean>;
    numericRangeErrors?: Record<string, boolean>;
    showReclassifyColumns?: boolean;
    resetKey?: string | number;
  }>(),
  {
    numericRanges: () => ({}),
    numericRangeLoading: () => ({}),
    numericRangeErrors: () => ({}),
  },
);

const emit = defineEmits<{
  (e: "update:show", show: boolean): void;
  (e: "update:filter", filter: ScGlobalFilter): void;
  (e: "search-options", payload: { field: string; search: string }): void;
  (e: "request-range", payload: { field: string; itemId?: string }): void;
}>();

const showModel = computed({
  get: () => props.show,
  set: (show: boolean) => emit("update:show", show),
});
const draftFilter = ref<ScGlobalFilter>(cloneScGlobalFilter(props.filter));
const activeCount = computed(() => scGlobalFilterConditionCount(draftFilter.value));
const hasChanges = computed(
  () => JSON.stringify(draftFilter.value) !== JSON.stringify(props.filter),
);

function updateDraft(filter: ScGlobalFilter): void {
  draftFilter.value = cloneScGlobalFilter(filter);
}

function cancel(): void {
  draftFilter.value = cloneScGlobalFilter(props.filter);
  showModel.value = false;
}

function apply(): void {
  if (hasChanges.value) emit("update:filter", cloneScGlobalFilter(draftFilter.value));
  showModel.value = false;
}

watch(
  () => props.show,
  (show) => {
    if (show) draftFilter.value = cloneScGlobalFilter(props.filter);
  },
  { immediate: true },
);

watch(
  () => props.filter,
  (filter) => {
    if (!props.show) draftFilter.value = cloneScGlobalFilter(filter);
  },
  { deep: true },
);
</script>

<template>
  <NModal
    v-model:show="showModel"
    preset="card"
    class="sc-global-filter-modal"
    data-testid="sc-global-filter-modal"
    closable
    :bordered="false"
    :style="{ width: 'min(880px, calc(100vw - 32px))' }"
  >
    <template #header>
      <div class="sc-global-filter-header">
        <span class="sc-global-filter-title">Global Filters</span>
        <NTag v-if="activeCount > 0" size="small" round type="success">
          {{ activeCount }} active
        </NTag>
      </div>
    </template>

    <ScGlobalFilterBar
      class="sc-global-filter-editor"
      :filter="draftFilter"
      :columns="columns"
      :distinct-values="distinctValues"
      :numeric-ranges="numericRanges"
      :numeric-range-loading="numericRangeLoading"
      :numeric-range-errors="numericRangeErrors"
      :show-reclassify-columns="showReclassifyColumns"
      :reset-key="resetKey"
      @update:filter="updateDraft"
      @search-options="emit('search-options', $event)"
      @request-range="emit('request-range', $event)"
    />

    <template #footer>
      <div class="sc-global-filter-footer">
        <NButton data-testid="sc-global-filter-cancel" size="small" @click="cancel">
          Cancel
        </NButton>
        <NButton
          data-testid="sc-global-filter-apply"
          type="primary"
          size="small"
          :disabled="!hasChanges"
          @click="apply"
        >
          Apply filters
        </NButton>
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
  align-items: center;
  gap: 8px;
  min-height: 22px;
}

.sc-global-filter-title {
  font-size: 17px;
  font-weight: 600;
  line-height: 22px;
}

.sc-global-filter-editor {
  margin: -4px 0;
}

.sc-global-filter-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}
</style>
