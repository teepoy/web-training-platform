<!--
  DashboardWidgetTemplate.vue
  ─────────────────────────
  Copy this file as the starting point for a new sidebar widget plugin.

  Steps:
    1. Copy to apps/web/src/plugins/widget-<your-key>/<YourWidget>.vue
    2. Rename the component.
    3. Replace the example logic with your own.
    4. Create index.ts in the same directory (see DashboardWidgetIndexTemplate.ts).
    5. Import and register the descriptor in apps/web/src/registrations/index.ts.
-->
<script setup lang="ts">
import { inject, computed } from "vue";
import {
  BROWSER_DASHBOARD_KEY,
  type DashboardWidgetProps,
} from "@platform/widget-sdk";

// ---------------------------------------------------------------------------
// Props — extend DashboardWidgetProps with your own widget-specific props.
// All props listed in your contract.acceptsProps must be declared here.
// ---------------------------------------------------------------------------

const props = withDefaults(
  defineProps<
    DashboardWidgetProps & {
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

const ctx = inject(BROWSER_DASHBOARD_KEY, {} as Record<string, unknown>);

const totalLoaded = computed(
  () => (ctx.totalLoaded as number | undefined) ?? 0,
);

// ---------------------------------------------------------------------------
// Inline data from panel descriptor
// ---------------------------------------------------------------------------

const inlineData = computed(
  () => (props.data?.inline as Record<string, unknown> | undefined) ?? {},
);
</script>

<template>
  <div class="sidebar-plugin-template">
    <p>Loaded: {{ totalLoaded }}</p>
    <!-- Replace this with your actual widget UI -->
    <pre>{{ inlineData }}</pre>
  </div>
</template>

<style scoped>
.sidebar-plugin-template {
  padding: 8px;
  font-size: 13px;
}
</style>
