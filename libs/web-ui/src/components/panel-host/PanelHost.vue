<!--
  PanelHost — reusable panel rendering host abstraction.

  Renders a list of `SidebarPanelDescriptor[]` outside of any sidebar shell,
  preserving all panel sub-element rendering: headers, collapse/expand,
  agent badges, WidgetErrorBoundary wrapping, and component resolution
  via a resolver prop.

  When provided, `context` and `interaction` props are injected so widgets
  resolve BROWSER_DASHBOARD_KEY and SIDEBAR_WIDGET_INTERACTION_KEY
  regardless of whether the host sits inside or outside a BrowserSidebar.

  CSS classes (.cs-panel, .cs-panel__header, etc.) are preserved verbatim
  for selector compatibility. All styles are self-contained (scoped);
  PanelHost does NOT depend on a `.cs` sidebar shell.
-->
<script setup lang="ts">
import {
  provide,
  ref,
  computed,
  type Component,
} from "vue";
import {
  SIDEBAR_WIDGET_INTERACTION_KEY,
  BROWSER_DASHBOARD_KEY,
  type SidebarWidgetInteractionContext,
} from "@platform/widget-sdk";
import type { SidebarPanelDescriptor } from "../../types/components";
import WidgetErrorBoundary from "../widget-error-boundary/WidgetErrorBoundary.vue";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

const props = defineProps<{
  panels: SidebarPanelDescriptor[];
  componentResolver?: (key: string) => Component | null | undefined;
  context?: Record<string, unknown>;
  interaction?: SidebarWidgetInteractionContext;
}>();

// ---------------------------------------------------------------------------
// Provide context to widgets (optional — only when props are explicitly passed)
// ---------------------------------------------------------------------------

if (props.context !== undefined) {
  provide(BROWSER_DASHBOARD_KEY, props.context);
}

const fallbackInteraction = computed<SidebarWidgetInteractionContext>(() => ({
  state: {
    activeLabelFilter: null,
    selectedLabels: [],
    collections: {},
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
  return props.componentResolver?.(key) ?? null;
}
</script>

<template>
  <div class="cs-panels">
    <div
      v-for="panel in panels"
      :key="panel.id"
      class="cs-panel"
      :class="{ 'cs-panel--agent': panel._agentOwned }"
      :data-testid="panel.id === 'wafer-map' ? 'wafer-map-panel' : undefined"
    >
      <div class="cs-panel__header" @click="togglePanel(panel)">
        <span class="cs-panel__title">{{ panel.title }}</span>
        <span v-if="panel._agentOwned" class="cs-panel__agent-badge">AI</span>
        <span
          class="cs-panel__chevron"
          :class="{ 'cs-panel__chevron--open': !isPanelCollapsed(panel) }"
        >&#9660;</span>
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
</template>

<style scoped>
/* ---------------------------------------------------------------------------
   Self-contained panel styles — identical to BrowserSidebar's .cs-panel
   namespace for selector compatibility. Does NOT depend on .cs sidebar shell.
   --------------------------------------------------------------------------- */

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
