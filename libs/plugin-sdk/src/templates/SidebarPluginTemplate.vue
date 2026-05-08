<!--
  SidebarPluginTemplate.vue
  ─────────────────────────
  Copy this file as the starting point for a new sidebar widget plugin.

  Steps:
    1. Copy to apps/web/src/plugins/sidebar-<your-key>/<YourWidget>.vue
    2. Rename the component.
    3. Replace the example logic with your own.
    4. Create index.ts in the same directory (see SidebarPluginIndexTemplate.ts).
    5. Import and register the descriptor in apps/web/src/plugins/index.ts.

  Bidirectional communication:
    App  → Widget : injected context (BROWSER_DASHBOARD_KEY) + interaction state (SIDEBAR_WIDGET_INTERACTION_KEY)
    Widget → App  : call interactionRef.value.dispatch(intent)
-->
<script setup lang="ts">
import { inject, computed } from "vue";
import {
  BROWSER_DASHBOARD_KEY,
  SIDEBAR_WIDGET_INTERACTION_KEY,
  type SidebarPluginRequiredProps,
  type SidebarWidgetIntent,
} from "@platform/plugin-sdk";

// ---------------------------------------------------------------------------
// Props — extend SidebarPluginRequiredProps with your own widget-specific props.
// All props listed in your contract.acceptsProps must be declared here.
// ---------------------------------------------------------------------------

const props = withDefaults(
  defineProps<
    SidebarPluginRequiredProps & {
      // Add widget-specific props here, e.g.:
      // myOption?: string
    }
  >(),
  {
    // myOption: 'default-value',
  },
);

// ---------------------------------------------------------------------------
// Read shared dashboard context (App → Widget)
// ---------------------------------------------------------------------------

// The context object passed via BrowserSidebar's :context prop.
// Keys depend on the surface — see docs/guides/sidebar-extension-guide.md.
const ctx = inject(BROWSER_DASHBOARD_KEY, {} as Record<string, unknown>);

// Example: read a value from the context
const totalLoaded = computed(
  () => (ctx.totalLoaded as number | undefined) ?? 0,
);

// ---------------------------------------------------------------------------
// Read + dispatch interaction state (bidirectional)
// ---------------------------------------------------------------------------

const interactionRef = inject(SIDEBAR_WIDGET_INTERACTION_KEY);
const activeLabel = computed(
  () => interactionRef?.value.state.activeLabelFilter ?? null,
);

function emitSampleSelection(ids: string[]) {
  interactionRef?.value.dispatch({
    type: "select-samples",
    operation: "replace",
    values: ids,
    sourcePanelId: "my-widget-panel-id", // should match the panel descriptor id
    metadata: {
      collection:
        (props.config?.interaction as { collection?: string } | undefined)
          ?.collection ?? "browser-items",
      entity: "sample",
      target: "both",
    },
  } satisfies SidebarWidgetIntent);
}

// ---------------------------------------------------------------------------
// Inline data from panel descriptor
// ---------------------------------------------------------------------------

// Access data injected via the panel descriptor's props.data.inline.*
// e.g. in DatasetDetailView: panel.props.data.inline.points = waferPoints.value
const inlineData = computed(
  () => (props.data?.inline as Record<string, unknown> | undefined) ?? {},
);
</script>

<template>
  <div class="sidebar-plugin-template">
    <p>Loaded: {{ totalLoaded }}</p>
    <p v-if="activeLabel">Active label: {{ activeLabel }}</p>
    <!-- Replace this with your actual widget UI -->
    <button @click="emitSampleSelection(['example-id'])">Select example</button>
  </div>
</template>

<style scoped>
.sidebar-plugin-template {
  padding: 8px;
  font-size: 13px;
}
</style>
