<script setup lang="ts">
import { provide } from "vue";
import type { SidebarPanelDescriptor } from "./sidebarConfig";
import type { ClassifyDashboardContext } from "../../composables/useClassifyDashboard";
import type { SidebarWidgetInteractionContext } from "./widgetContract";
import BrowserSidebar from "../../components/sample-browser/BrowserSidebar.vue";

const props = defineProps<{
  panels: SidebarPanelDescriptor[];
  context: ClassifyDashboardContext;
  interaction?: SidebarWidgetInteractionContext;
  collapsed?: boolean;
}>();

const emit = defineEmits<{
  "update:collapsed": [value: boolean];
}>();

// Keep backward compatibility for widgets injecting "classifyDashboard"
provide("classifyDashboard", props.context);
</script>

<template>
  <BrowserSidebar
    :panels="props.panels"
    :context="(props.context as unknown as Record<string, unknown>)"
    :interaction="props.interaction"
    :collapsed="props.collapsed"
    @update:collapsed="emit('update:collapsed', $event)"
  />
</template>
