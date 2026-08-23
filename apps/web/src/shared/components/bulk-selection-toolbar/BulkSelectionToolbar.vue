<script setup lang="ts">
import { NButton, NIcon, NSpace, NText, NTooltip } from "naive-ui";
import { CloseCircleOutline } from "@vicons/ionicons5";

defineProps<{
  selectedCount: number;
  itemLabel: string;
  loading?: boolean;
}>();

defineEmits<{
  clear: [];
}>();
</script>

<template>
  <div
    v-if="selectedCount > 0"
    class="bulk-selection-toolbar"
    role="toolbar"
    :aria-label="`${itemLabel} bulk actions`"
    data-testid="bulk-selection-toolbar"
  >
    <NText strong>
      {{ selectedCount }} {{ itemLabel }}{{ selectedCount === 1 ? "" : "s" }} selected
    </NText>
    <NSpace align="center" :size="8">
      <slot />
      <NTooltip trigger="hover">
        <template #trigger>
          <NButton
            size="small"
            quaternary
            circle
            aria-label="Clear selection"
            :disabled="loading"
            @click="$emit('clear')"
          >
            <template #icon>
              <NIcon><CloseCircleOutline /></NIcon>
            </template>
          </NButton>
        </template>
        Clear selection
      </NTooltip>
    </NSpace>
  </div>
</template>

<style scoped>
.bulk-selection-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 42px;
  margin: 0 0 12px;
  padding: 8px 12px;
  border: 1px solid rgba(24, 160, 88, 0.28);
  border-radius: 6px;
  background: rgba(24, 160, 88, 0.08);
}

@media (max-width: 640px) {
  .bulk-selection-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
