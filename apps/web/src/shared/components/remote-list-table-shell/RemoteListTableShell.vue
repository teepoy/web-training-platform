<script setup lang="ts">
import { NAlert, NDataTable, NEmpty } from "naive-ui";
import { useI18n } from "vue-i18n";

defineOptions({ inheritAttrs: false });

withDefaults(
  defineProps<{
    loading: boolean;
    error?: string | null;
    activeFilterCount?: number;
    emptyDescription: string;
    noResultsDescription?: string;
  }>(),
  { error: null, activeFilterCount: 0, noResultsDescription: undefined },
);
const { t } = useI18n();
</script>

<template>
  <NAlert v-if="error" type="error" role="alert">{{ error }}</NAlert>
  <NDataTable v-else v-bind="$attrs" :loading="loading">
    <template #empty>
      <NEmpty
        :description="
          activeFilterCount > 0
            ? noResultsDescription || t('common.noMatchingResults')
            : emptyDescription
        "
      >
        <template v-if="$slots['empty-extra']" #extra>
          <slot name="empty-extra" />
        </template>
      </NEmpty>
    </template>
  </NDataTable>
</template>
