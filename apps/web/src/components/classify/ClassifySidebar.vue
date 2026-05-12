<script setup lang="ts">
import { BrowserSidebar } from "@platform/web-ui";
import type { SidebarPanelDescriptor } from "./sidebarConfig";
import type { SidebarWidgetInteractionContext } from "./widgetContract";
import { widgetRegistry } from "../../core/registry";
import {
  COLLAPSED_SIDEBAR_WIDTH,
  MAX_SIDEBAR_WIDTH,
  MIN_SIDEBAR_WIDTH,
  useSampleBrowserPrefs,
} from "@platform/web-ui";

const props = defineProps<{
  panels: SidebarPanelDescriptor[];
  context: Record<string, unknown>;
  interaction?: SidebarWidgetInteractionContext;
  collapsed?: boolean;
}>();

const emit = defineEmits<{
  "update:collapsed": [value: boolean];
}>();

const prefs = useSampleBrowserPrefs();
</script>

<template>
  <BrowserSidebar
    :panels="props.panels"
    :context="props.context"
    :interaction="props.interaction"
    :collapsed="props.collapsed"
    :sidebar-width="prefs.sidebarWidth"
    :min-sidebar-width="MIN_SIDEBAR_WIDTH"
    :max-sidebar-width="MAX_SIDEBAR_WIDTH"
    :collapsed-sidebar-width="COLLAPSED_SIDEBAR_WIDTH"
    :component-resolver="(key: string) => widgetRegistry.getWidgetComponent(key) ?? null"
    @update:collapsed="emit('update:collapsed', $event)"
    @update:sidebar-width="prefs.setSidebarWidth"
  />
</template>
