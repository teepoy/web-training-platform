<script setup lang="ts">
import { NButton, NInput, NSelect } from "naive-ui";
import type { CreatorSummary } from "@/generated/orval/models";
import CreatorScopeSelect from "@/shared/components/creator-scope-select";
import type { ModelSourceType } from "../composables/useModelSearch";

defineProps<{
  keyword: string;
  sourceType: ModelSourceType | null;
  creatorScope: string;
  creators: CreatorSummary[];
  creatorsLoading: boolean;
  activeFilterCount: number;
}>();

const emit = defineEmits<{
  (event: "update:keyword", value: string): void;
  (event: "update:sourceType", value: ModelSourceType | null): void;
  (event: "update:creatorScope", value: string): void;
  (event: "clear"): void;
}>();

const sourceOptions = [
  { label: "Dataset", value: "dataset" },
  { label: "Collection", value: "collection" },
];
</script>

<template>
  <div class="model-search-filters" data-testid="model-search-filters">
    <NInput
      :value="keyword"
      size="small"
      clearable
      placeholder="Search models"
      @update:value="emit('update:keyword', $event)"
    />
    <NSelect
      :value="sourceType"
      size="small"
      clearable
      :options="sourceOptions"
      placeholder="All training sources"
      @update:value="emit('update:sourceType', $event as ModelSourceType | null)"
    />
    <CreatorScopeSelect
      :model-value="creatorScope"
      :creators="creators"
      :loading="creatorsLoading"
      resource-label="models"
      @update:model-value="emit('update:creatorScope', $event)"
    />
    <NButton v-if="activeFilterCount > 0" size="small" quaternary @click="emit('clear')">
      Clear filters ({{ activeFilterCount }})
    </NButton>
  </div>
</template>

<style scoped>
.model-search-filters {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) minmax(170px, 220px) minmax(170px, 220px) auto;
  gap: 8px;
  align-items: center;
}

@media (max-width: 760px) {
  .model-search-filters {
    grid-template-columns: 1fr;
    align-items: stretch;
  }
}
</style>
