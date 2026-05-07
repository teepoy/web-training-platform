/**
 * SidebarPluginIndexTemplate.ts
 * ─────────────────────────────
 * Copy this as apps/web/src/plugins/sidebar-<your-key>/index.ts
 * and edit to match your widget.
 */

import { defineAsyncComponent } from "vue";
import { defineSidebarPlugin } from "@platform/plugin-sdk";

export const myWidgetPlugin = defineSidebarPlugin({
  key: "my-widget", // ← must be unique; used in panel descriptors
  component: defineAsyncComponent(() => import("./MyWidget.vue")),
  contract: {
    displayName: "My Widget",
    description: "One-line description of what this widget shows.",
    // List every prop name your component accepts (excluding SidebarPluginRequiredProps base props).
    acceptsProps: ["myOption"],
    capabilities: {
      reads: ["browser-dashboard"], // context keys your widget injects
      emits: [], // intent types your widget dispatches
    },
    selfTests: [
      {
        name: "renders without crashing",
        objective: "Verify the widget mounts with no context provided.",
        steps: ["Render the widget with no extra props or context."],
        expected: ["The widget renders without throwing."],
      },
    ],
  },
});
