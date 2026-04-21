<!--
  ClassifySidebar — dynamic, composable sidebar for the classify view.

  Renders panels from a descriptor array (see sidebarConfig.ts).  Each panel
  is resolved to a Vue component at render time and receives its `props` bag
  as v-bind attributes.

  The sidebar provides the ClassifyDashboardContext via `provide` so widgets
  don't need explicit prop-drilling for shared data.

  Agent-controlled panels (marked _agentOwned) receive their data/config/size
  as props and are wrapped in a WidgetErrorBoundary.
-->
<script setup lang="ts">
import { provide, ref, computed, type Component } from "vue";
import {
  WIDGET_COMPONENTS,
  type SidebarPanelDescriptor,
} from "./sidebarConfig";
import type { ClassifyDashboardContext } from "../../composables/useClassifyDashboard";
import {
  SIDEBAR_WIDGET_INTERACTION_KEY,
  type SidebarWidgetInteractionContext,
} from "./widgetContract";
import WidgetErrorBoundary from "./widgets/WidgetErrorBoundary.vue";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

const props = defineProps<{
  panels: SidebarPanelDescriptor[];
  context: ClassifyDashboardContext;
  interaction?: SidebarWidgetInteractionContext;
  collapsed?: boolean;
}>();

const emit = defineEmits<{
  "update:collapsed": [value: boolean];
}>();

// ---------------------------------------------------------------------------
// Provide context to widgets
// ---------------------------------------------------------------------------

provide("classifyDashboard", props.context);

const fallbackInteraction = computed<SidebarWidgetInteractionContext>(() => ({
  state: {
    activeLabelFilter: null,
    selectedLabels: [],
  },
  dispatch: () => undefined,
}));

const interactionContext = computed(
  () => props.interaction ?? fallbackInteraction.value,
);

provide(SIDEBAR_WIDGET_INTERACTION_KEY, interactionContext);

// ---------------------------------------------------------------------------
// Panel collapse state (per panel)
// ---------------------------------------------------------------------------

const panelCollapsed = ref<Record<string, boolean>>({});

function isPanelCollapsed(panel: SidebarPanelDescriptor): boolean {
  return panelCollapsed.value[panel.id] ?? panel.collapsed ?? false;
}

function togglePanel(panel: SidebarPanelDescriptor): void {
  panelCollapsed.value = {
    ...panelCollapsed.value,
    [panel.id]: !isPanelCollapsed(panel),
  };
}

// ---------------------------------------------------------------------------
// Component resolution
// ---------------------------------------------------------------------------

function resolveComponent(key: string): Component | null {
  return WIDGET_COMPONENTS[key] ?? null;
}

// Sidebar-level collapse toggle
const sidebarCollapsed = computed({
  get: () => props.collapsed ?? false,
  set: (v) => emit("update:collapsed", v),
});
</script>

<template>
  <aside class="cs" :class="{ 'cs--collapsed': sidebarCollapsed }">
    <div class="cs-header">
      <span v-if="!sidebarCollapsed" class="cs-header__title">Dashboard</span>
      <button
        class="cs-header__toggle"
        @click="sidebarCollapsed = !sidebarCollapsed"
        :title="sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
      >
        {{ sidebarCollapsed ? "&#9664;" : "&#9654;" }}
      </button>
    </div>

    <div v-if="!sidebarCollapsed" class="cs-panels">
      <div
        v-for="panel in panels"
        :key="panel.id"
        class="cs-panel"
        :class="{ 'cs-panel--agent': panel._agentOwned }"
      >
        <div class="cs-panel__header" @click="togglePanel(panel)">
          <span class="cs-panel__title">{{ panel.title }}</span>
          <span v-if="panel._agentOwned" class="cs-panel__agent-badge">AI</span>
          <span
            class="cs-panel__chevron"
            :class="{ 'cs-panel__chevron--open': !isPanelCollapsed(panel) }"
            >&#9660;</span
          >
        </div>

        <div v-show="!isPanelCollapsed(panel)" class="cs-panel__body">
          <WidgetErrorBoundary
            v-if="resolveComponent(panel.component)"
            :widget-id="panel.id"
            :widget-component="panel.component"
          >
            <component
              :is="resolveComponent(panel.component)"
              v-bind="panel.props"
            />
          </WidgetErrorBoundary>
          <div v-else class="cs-panel__missing">
            Unknown widget: {{ panel.component }}
          </div>
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.cs {
  display: flex;
  flex-direction: column;
  width: 280px;
  min-width: 280px;
  border-left: 1px solid var(--cv-border, rgba(255, 255, 255, 0.12));
  background: var(--cv-card-bg, #1e1e2e);
  overflow-y: auto;
  transition:
    width 0.2s,
    min-width 0.2s;
}

.cs--collapsed {
  width: 36px;
  min-width: 36px;
}

.cs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid var(--cv-border, rgba(255, 255, 255, 0.08));
}

.cs-header__title {
  font-size: 13px;
  font-weight: 700;
  color: var(--cv-text, #fff);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.cs-header__toggle {
  background: none;
  border: none;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.45));
  cursor: pointer;
  font-size: 11px;
  padding: 2px 4px;
  border-radius: 4px;
}

.cs-header__toggle:hover {
  background: rgba(255, 255, 255, 0.08);
}

.cs-panels {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px;
}

.cs-panel {
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.02);
  overflow: hidden;
}

.cs-panel--agent {
  border-left: 2px solid rgba(91, 106, 191, 0.4);
}

.cs-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  cursor: pointer;
  user-select: none;
  gap: 6px;
}

.cs-panel__header:hover {
  background: rgba(255, 255, 255, 0.04);
}

.cs-panel__title {
  font-size: 12px;
  font-weight: 600;
  color: var(--cv-text, rgba(255, 255, 255, 0.85));
  flex: 1;
}

.cs-panel__agent-badge {
  font-size: 9px;
  font-weight: 700;
  color: #7c8aff;
  background: rgba(124, 138, 255, 0.12);
  padding: 1px 5px;
  border-radius: 3px;
  flex-shrink: 0;
}

.cs-panel__chevron {
  font-size: 9px;
  color: rgba(255, 255, 255, 0.35);
  transition: transform 0.15s;
  transform: rotate(-90deg);
  flex-shrink: 0;
}

.cs-panel__chevron--open {
  transform: rotate(0deg);
}

.cs-panel__body {
  padding: 4px 10px 12px;
}

.cs-panel__missing {
  font-size: 12px;
  color: rgba(255, 200, 100, 0.7);
  padding: 8px 0;
}
</style>
