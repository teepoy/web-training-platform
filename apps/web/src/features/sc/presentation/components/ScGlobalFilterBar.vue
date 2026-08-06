<script setup lang="ts">
import type { ScGlobalFilter } from "@/features/sc/domain/globalFilter";
import ScGlobalFilterQueryBuilder from "./ScGlobalFilterQueryBuilder.vue";

withDefaults(
  defineProps<{
    filter: ScGlobalFilter;
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
  (event: "update:filter", filter: ScGlobalFilter): void;
  (event: "search-options", payload: { field: string; search: string }): void;
  (event: "request-range", payload: { field: string; itemId?: string }): void;
}>();
</script>

<template>
  <ScGlobalFilterQueryBuilder
    v-bind="$props"
    @update:filter="emit('update:filter', $event)"
    @search-options="emit('search-options', $event)"
    @request-range="emit('request-range', $event)"
  />
</template>
