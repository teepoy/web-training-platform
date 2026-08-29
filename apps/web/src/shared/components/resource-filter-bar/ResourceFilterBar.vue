<script setup lang="ts">
import { NButton, NInput } from "naive-ui";
import type { CreatorSummary } from "@/generated/orval/models";
import CreatorScopeSelect from "@/shared/components/creator-scope-select";

withDefaults(
  defineProps<{
    keyword: string;
    keywordPlaceholder: string;
    creatorScope: string;
    creators: CreatorSummary[];
    creatorsLoading?: boolean;
    activeFilterCount: number;
    resourceLabel?: string;
    searchTestId?: string;
  }>(),
  { creatorsLoading: false, resourceLabel: "resources", searchTestId: undefined },
);

const emit = defineEmits<{
  (event: "update:keyword", value: string): void;
  (event: "update:creatorScope", value: string): void;
  (event: "clear"): void;
}>();
</script>

<template>
  <div class="resource-filter-bar" data-testid="resource-filter-bar">
    <NInput
      :value="keyword"
      size="small"
      clearable
      :placeholder="keywordPlaceholder"
      class="resource-filter-bar__search"
      :data-testid="searchTestId"
      @update:value="emit('update:keyword', $event)"
    />
    <CreatorScopeSelect
      :model-value="creatorScope"
      :creators="creators"
      :loading="creatorsLoading"
      :resource-label="resourceLabel"
      class="resource-filter-bar__creator"
      @update:model-value="emit('update:creatorScope', $event)"
    />
    <slot name="filters" />
    <NButton v-if="activeFilterCount > 0" size="small" quaternary @click="emit('clear')">
      Clear filters ({{ activeFilterCount }})
    </NButton>
    <div v-if="$slots.actions" class="resource-filter-bar__actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<style scoped>
.resource-filter-bar {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 12px 0;
}

.resource-filter-bar__search {
  width: min(420px, 100%);
}

.resource-filter-bar__creator {
  width: min(240px, 100%);
}

.resource-filter-bar__actions {
  flex: none;
  margin-left: auto;
}

@media (max-width: 640px) {
  .resource-filter-bar {
    align-items: stretch;
    flex-direction: column;
  }

  .resource-filter-bar__search,
  .resource-filter-bar__creator,
  .resource-filter-bar__actions,
  .resource-filter-bar__actions :deep(.n-button) {
    width: 100%;
  }

  .resource-filter-bar__actions {
    margin-left: 0;
  }
}
</style>
