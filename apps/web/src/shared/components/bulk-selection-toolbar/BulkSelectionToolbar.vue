<script setup lang="ts">
import { NButton, NIcon, NSpace, NText, NTooltip } from "naive-ui";
import { CloseCircleOutline } from "@vicons/ionicons5";
import { useI18n } from "vue-i18n";

defineProps<{
  selectedCount: number;
  itemLabel: string;
  loading?: boolean;
}>();

defineEmits<{
  clear: [];
}>();
const { t } = useI18n();

function selectedLabel(count: number, item: string): string {
  return t(count === 1 ? "common.selectedOne" : "common.selectedMany", { count, item });
}
</script>

<template>
  <div
    v-if="selectedCount > 0"
    class="bulk-selection-toolbar"
    role="toolbar"
    :aria-label="t('common.bulkActions', { item: itemLabel })"
    data-testid="bulk-selection-toolbar"
  >
    <NText strong>
      {{ selectedLabel(selectedCount, itemLabel) }}
    </NText>
    <NSpace align="center" :size="8">
      <slot />
      <NTooltip trigger="hover">
        <template #trigger>
          <NButton
            size="small"
            quaternary
            circle
            :aria-label="t('common.clearSelection')"
            :disabled="loading"
            @click="$emit('clear')"
          >
            <template #icon>
              <NIcon><CloseCircleOutline /></NIcon>
            </template>
          </NButton>
        </template>
        {{ t("common.clearSelection") }}
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
