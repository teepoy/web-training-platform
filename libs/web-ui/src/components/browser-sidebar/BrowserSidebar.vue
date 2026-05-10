<script setup lang="ts">
import { provide, ref, computed, watch, type Component } from "vue";
import {
  SIDEBAR_WIDGET_INTERACTION_KEY,
  BROWSER_DASHBOARD_KEY,
  type SidebarWidgetInteractionContext,
} from "@platform/plugin-sdk";
import type { SidebarPanelDescriptor } from "../../types/components";
import WidgetErrorBoundary from "../widget-error-boundary/WidgetErrorBoundary.vue";

const DEFAULT_SIDEBAR_WIDTH = 280;
const MIN_SIDEBAR_WIDTH = 200;
const MAX_SIDEBAR_WIDTH = 520;
const COLLAPSED_SIDEBAR_WIDTH = 36;

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

const props = defineProps<{
  panels: SidebarPanelDescriptor[];
  context: Record<string, unknown>;
  interaction?: SidebarWidgetInteractionContext;
  collapsed?: boolean;
  componentResolver?: (key: string) => Component | null | undefined;
  sidebarWidth?: number;
  minSidebarWidth?: number;
  maxSidebarWidth?: number;
  collapsedSidebarWidth?: number;
}>();

const emit = defineEmits<{
  "update:collapsed": [value: boolean];
  "update:sidebarWidth": [value: number];
}>();

// ---------------------------------------------------------------------------
// Provide context to widgets
// ---------------------------------------------------------------------------

provide(BROWSER_DASHBOARD_KEY, props.context);

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
  return props.componentResolver?.(key) ?? null;
}

// Sidebar-level collapse toggle
const sidebarCollapsed = computed({
  get: () => props.collapsed ?? false,
  set: (v) => emit("update:collapsed", v),
});

// ---------------------------------------------------------------------------
// Resize logic
// ---------------------------------------------------------------------------

const isResizing = ref(false);
const visualWidth = ref(props.sidebarWidth ?? DEFAULT_SIDEBAR_WIDTH);

watch(() => props.sidebarWidth, (val) => {
  if (!isResizing.value) {
    visualWidth.value = val ?? DEFAULT_SIDEBAR_WIDTH;
  }
});

let startX = 0;
let startWidth = 0;

function onResizeStart(e: PointerEvent) {
  if (e.currentTarget instanceof Element) {
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  isResizing.value = true;
  startX = e.clientX;
  startWidth = props.sidebarWidth ?? DEFAULT_SIDEBAR_WIDTH;
  visualWidth.value = startWidth;
}

function onResizeMove(e: PointerEvent) {
  if (!isResizing.value) return;
  // Since the sidebar is on the right, dragging left increases width
  const dx = startX - e.clientX;
  const maxWidth = props.maxSidebarWidth ?? MAX_SIDEBAR_WIDTH;
  const minWidth = props.minSidebarWidth ?? MIN_SIDEBAR_WIDTH;
  const newWidth = Math.min(maxWidth, Math.max(minWidth, startWidth + dx));
  visualWidth.value = newWidth;
}

function onResizeEnd(e: PointerEvent) {
  if (!isResizing.value) return;
  isResizing.value = false;
  if (e.currentTarget instanceof Element) {
    e.currentTarget.releasePointerCapture(e.pointerId);
  }
  emit("update:sidebarWidth", visualWidth.value);
}

const currentWidth = computed(() => {
  return sidebarCollapsed.value ? (props.collapsedSidebarWidth ?? COLLAPSED_SIDEBAR_WIDTH) : visualWidth.value;
});
</script>

<template>
  <aside 
    class="cs" 
    :class="{ 'cs--collapsed': sidebarCollapsed, 'cs--resizing': isResizing }"
    :style="{ width: currentWidth + 'px', minWidth: currentWidth + 'px' }"
    data-testid="browser-sidebar"
  >
    <div
      v-if="!sidebarCollapsed"
      data-testid="browser-sidebar-resize-handle"
      class="sidebar-resize-handle"
      @pointerdown="onResizeStart"
      @pointermove="onResizeMove"
      @pointerup="onResizeEnd"
      @pointercancel="onResizeEnd"
    />
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
        :data-testid="panel.id === 'wafer-map' ? 'wafer-map-panel' : undefined"
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
  position: relative;
  border-left: 1px solid var(--cv-border, rgba(255, 255, 255, 0.12));
  background: var(--cv-card-bg, #1e1e2e);
  overflow-y: auto;
  transition:
    width 0.2s,
    min-width 0.2s;
}

.cs::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
.cs::-webkit-scrollbar-track {
  background: transparent;
}
.cs::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
}
.cs::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.2);
}

.cs--collapsed {
  /* collapsed width is handled by inline style */
}

.cs--resizing {
  transition: none !important;
  user-select: none;
}

.sidebar-resize-handle {
  position: absolute;
  top: 0;
  bottom: 0;
  left: -4px;
  width: 10px;
  cursor: col-resize;
  z-index: 10;
  background: transparent;
}
.sidebar-resize-handle:hover,
.cs--resizing .sidebar-resize-handle {
  background: rgba(255, 255, 255, 0.05);
  border-left: 1px solid rgba(255, 255, 255, 0.1);
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
