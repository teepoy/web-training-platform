<script setup lang="ts">
import { NAlert, NDataTable, NEmpty } from "naive-ui";

defineOptions({ inheritAttrs: false });

withDefaults(
  defineProps<{
    loading: boolean;
    error?: string | null;
    activeFilterCount?: number;
    emptyDescription: string;
    noResultsDescription?: string;
  }>(),
  { error: null, activeFilterCount: 0, noResultsDescription: "No matching results" },
);
</script>

<template>
  <NAlert v-if="error" type="error" role="alert">{{ error }}</NAlert>
  <NDataTable v-else v-bind="$attrs" :loading="loading">
    <template #empty>
      <NEmpty :description="activeFilterCount > 0 ? noResultsDescription : emptyDescription">
        <template v-if="$slots['empty-extra']" #extra>
          <slot name="empty-extra" />
        </template>
      </NEmpty>
    </template>
  </NDataTable>
</template>
