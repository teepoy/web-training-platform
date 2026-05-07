/**
 * @platform/plugin-sdk
 *
 * Public API surface for plugin authors.
 */

// Sidebar widget contracts + interaction system
export type {
  SidebarPluginDescriptor,
  SidebarPluginRequiredProps,
  SidebarWidgetContract,
  SidebarWidgetCapability,
  SidebarWidgetSelfTestScenario,
  SidebarWidgetContextKey,
  SidebarWidgetIntentType,
  SidebarWidgetOperation,
  SidebarWidgetCollectionEntity,
  SidebarWidgetSource,
  SidebarWidgetIntentTarget,
  SidebarWidgetFilterMode,
  SidebarWidgetIntentMetadata,
  SidebarWidgetIntent,
  SidebarWidgetCollectionSelectionState,
  SidebarWidgetCollectionFilterState,
  SidebarWidgetCollectionState,
  SidebarWidgetInteractionState,
  SidebarWidgetInteractionConfig,
  SidebarWidgetInteractionContext,
} from "./sidebar";

export {
  BROWSER_DASHBOARD_KEY,
  SIDEBAR_WIDGET_INTERACTION_KEY,
  defineSidebarPlugin,
  reduceLabelFilterIntent,
  reduceCollectionIntent,
} from "./sidebar";

// Importer contracts
export type {
  ImportPluginDescriptor,
  ImportPluginSurface,
  ImportPluginRequiredProps,
  ImportPluginResult,
} from "./importer";

export { defineImportPlugin } from "./importer";

// Exporter contracts
export type {
  ExportPluginDescriptor,
  ExportPluginSurface,
  ExportPluginRequiredProps,
  ExportPluginResult,
} from "./exporter";

export { defineExportPlugin } from "./exporter";

// Agent skill contracts
export type {
  AgentSkillDescriptor,
  AgentSkillSurface,
  AgentSkillResultProps,
} from "./agent";

export { defineAgentSkill } from "./agent";

// Registry
export type { PluginRegistry } from "./registry";
export { createPluginRegistry } from "./registry";
