<script setup lang="ts">
import { NCard, NSpace, NText } from "naive-ui";

import type { PluginCard } from "../plugin-flow";

defineProps<{
  plugins: PluginCard[];
  title?: string;
}>();

const emit = defineEmits<{
  select: [plugin: PluginCard];
}>();
</script>

<template>
  <div class="plugin-type-selector">
    <NText v-if="title" tag="h3" style="margin: 0 0 16px">{{ title }}</NText>
    <NSpace vertical size="medium">
      <NCard
        v-for="plugin in plugins"
        :key="plugin.id"
        hoverable
        size="small"
        style="cursor: pointer"
        @click="emit('select', plugin)"
      >
        <div style="display: flex; align-items: center; gap: 12px">
          <span v-if="plugin.icon" class="plugin-type-icon">{{ plugin.icon }}</span>
          <div style="flex: 1; min-width: 0">
            <NText tag="div" style="font-weight: 500">{{ plugin.label }}</NText>
            <NText v-if="plugin.description" tag="div" depth="3" style="font-size: 13px; margin-top: 2px">
              {{ plugin.description }}
            </NText>
          </div>
        </div>
      </NCard>
    </NSpace>
    <NText v-if="plugins.length === 0" depth="3" style="display: block; text-align: center; padding: 24px 0">
      No plugins available.
    </NText>
  </div>
</template>

<style scoped>
.plugin-type-icon {
  font-size: 24px;
  width: 32px;
  text-align: center;
  flex-shrink: 0;
}
</style>
