<script setup lang="ts">
import { NCard, NSpace, NText } from "naive-ui";

import type { FlowCard } from "../../flow";

defineProps<{
  flows: FlowCard[];
  title?: string;
}>();

const emit = defineEmits<{
  select: [flow: FlowCard];
}>();
</script>

<template>
  <div class="flow-type-selector">
    <NText v-if="title" tag="h3" style="margin: 0 0 16px">{{ title }}</NText>
    <NSpace vertical size="medium">
      <NCard
        v-for="flow in flows"
        :key="flow.id"
        hoverable
        size="small"
        role="button"
        tabindex="0"
        :aria-label="flow.label"
        style="cursor: pointer"
        @click="emit('select', flow)"
        @keydown.enter="emit('select', flow)"
        @keydown.space.prevent="emit('select', flow)"
      >
        <div style="display: flex; align-items: center; gap: 12px">
          <span v-if="flow.icon" class="flow-type-icon">{{ flow.icon }}</span>
          <div style="flex: 1; min-width: 0">
            <NText tag="div" style="font-weight: 500">{{ flow.label }}</NText>
            <NText
              v-if="flow.description"
              tag="div"
              depth="3"
              style="font-size: 13px; margin-top: 2px"
            >
              {{ flow.description }}
            </NText>
          </div>
        </div>
      </NCard>
    </NSpace>
    <NText
      v-if="flows.length === 0"
      depth="3"
      style="display: block; text-align: center; padding: 24px 0"
    >
      No importers or exporters available.
    </NText>
  </div>
</template>

<style scoped>
.flow-type-icon {
  font-size: 24px;
  width: 32px;
  text-align: center;
  flex-shrink: 0;
}
</style>
