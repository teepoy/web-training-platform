/**
 * apps/web/src/core/registry.ts
 *
 * Singleton DescriptorRegistry for the web app.
 * Populated in apps/web/src/registrations/index.ts before app mount.
 * Consumed by app surfaces that pass component resolvers into BrowserSidebar,
 * DatasetDetailView (import/export dropdowns),
 * and the agent composables.
 */

import { createDescriptorRegistry } from "@platform/widget-sdk";

export const widgetRegistry = createDescriptorRegistry();
