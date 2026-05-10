<script setup lang="ts">
import { computed } from 'vue'
import { NDrawer, NDrawerContent, NImage, NDescriptions, NDescriptionsItem, NEmpty, NTag } from 'naive-ui'
import type { PreviewItem } from '../../types/components'

const props = defineProps<{
  show: boolean
  item: PreviewItem | null
}>()

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
}>()

const metadataEntries = computed(() => {
  if (!props.item) return []
  return Object.entries(props.item.metadata).map(([key, value]) => ({
    key,
    value: typeof value === 'object' ? JSON.stringify(value) : String(value),
  }))
})
</script>

<template>
  <NDrawer
    :show="show"
    :width="400"
    placement="right"
    @update:show="emit('update:show', $event)"
  >
    <NDrawerContent title="Item Preview" :native-scrollbar="false" closable>
      <template v-if="item">
        <NImage
          :src="item.image_uris[0]"
          object-fit="contain"
          style="width: 100%; max-height: 300px; border-radius: 4px; margin-bottom: 16px;"
        />
        <div style="margin-bottom: 8px; font-size: 12px; color: var(--n-text-color-3);">
          ID: {{ item.upstream_item_id }}
        </div>
        <div v-if="metadataEntries.length > 0">
          <div style="font-size: 12px; font-weight: 600; margin-bottom: 8px; color: var(--n-text-color-2);">Metadata</div>
          <NDescriptions :column="1" size="small" bordered>
            <NDescriptionsItem v-for="entry in metadataEntries" :key="entry.key" :label="entry.key">
              {{ entry.value }}
            </NDescriptionsItem>
          </NDescriptions>
        </div>
        <NEmpty v-else description="No metadata" style="margin-top: 24px;" />
      </template>
      <NEmpty v-else description="No item selected" />
    </NDrawerContent>
  </NDrawer>
</template>
