/**
 * apps/web/src/core/registry.ts
 *
 * Singleton PluginRegistry for the web app.
 * Populated in apps/web/src/plugins/index.ts before app mount.
 * Consumed by BrowserSidebar, DatasetDetailView (import/export dropdowns),
 * and the agent composables.
 */

import { createPluginRegistry } from "@platform/plugin-sdk";

export const pluginRegistry = createPluginRegistry();
