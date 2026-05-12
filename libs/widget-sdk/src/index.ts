/**
 * @platform/widget-sdk
 *
 * Public API surface for widget authors.
 */

// Sidebar widget contracts
export type {
  DashboardWidgetDescriptor,
  DashboardWidgetProps,
  WidgetContract,
  SidebarWidgetCapability,
  SidebarWidgetSelfTestScenario,
} from "./sidebar";

export {
  BROWSER_DASHBOARD_KEY,
  defineDashboardWidget,
} from "./sidebar";

// Importer contracts
export type {
  ImporterDescriptor,
  ImporterSurface,
  ImporterProps,
  ImporterResult,
} from "./importer";

export { defineImporter } from "./importer";

// Exporter contracts
export type {
  ExporterDescriptor,
  ExporterSurface,
  ExporterProps,
  ExporterResult,
} from "./exporter";

export { defineExporter } from "./exporter";

// Agent skill contracts
export type {
  AgentSkillDescriptor,
  AgentSkillSurface,
  AgentSkillResultProps,
} from "./agent";

export { defineAgentSkill } from "./agent";

// Preview launcher contracts
export type {
  PreviewLauncherDescriptor,
  PreviewLauncherSurface,
  PreviewLauncherRequiredProps,
  PreviewLauncherResult,
} from "./preview";

export { definePreviewLauncher } from "./preview";

// Registry
export type { DescriptorRegistry } from "./registry";
export { createDescriptorRegistry } from "./registry";
