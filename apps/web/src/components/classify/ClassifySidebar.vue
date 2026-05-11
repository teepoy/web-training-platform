<script setup lang="ts">
import { provide } from "vue";
import { BrowserSidebar } from "@platform/web-ui";
import type { SidebarPanelDescriptor } from "./sidebarConfig";
import type { ClassifyDashboardContext } from "../../composables/useClassifyDashboard";
import type { SidebarWidgetInteractionContext } from "./widgetContract";
import { pluginRegistry } from "../../core/registry";
import {
  COLLAPSED_SIDEBAR_WIDTH,
  MAX_SIDEBAR_WIDTH,
  MIN_SIDEBAR_WIDTH,
  useSampleBrowserPrefs,
} from "@platform/web-ui";

const props = defineProps<{
  panels: SidebarPanelDescriptor[];
  context: ClassifyDashboardContext;
  interaction?: SidebarWidgetInteractionContext;
  collapsed?: boolean;
}>();

const emit = defineEmits<{
  "update:collapsed": [value: boolean];
}>();

const prefs = useSampleBrowserPrefs();

// Keep backward compatibility for widgets injecting "classifyDashboard"
provide("classifyDashboard", props.context);
</script>

<template>
  <BrowserSidebar
    :panels="props.panels"
    :context="(props.context as unknown as Record<string, unknown>)"
    :interaction="props.interaction"
    :collapsed="props.collapsed"
    :sidebar-width="prefs.sidebarWidth"
    :min-sidebar-width="MIN_SIDEBAR_WIDTH"
    :max-sidebar-width="MAX_SIDEBAR_WIDTH"
    :collapsed-sidebar-width="COLLAPSED_SIDEBAR_WIDTH"
    :component-resolver="(key) => pluginRegistry.getSidebarComponent(key) ?? null"
    @update:collapsed="emit('update:collapsed', $event)"
    @update:sidebar-width="prefs.setSidebarWidth"
  />
</template>
