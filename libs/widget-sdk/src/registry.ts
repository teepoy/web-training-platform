/**
 * @platform/widget-sdk — Widget registry
 *
 * The registry is a singleton created once in apps/web/src/core/registry.ts
 * and populated in apps/web/src/registrations/index.ts before app mount.
 *
 * Widget modules export descriptors created with define* helpers.
 * The app registration barrel imports those descriptors and calls:
 *   widgetRegistry.registerWidget(dashboardDescriptor)
 *   widgetRegistry.registerImporter(importerDescriptor)
 *   widgetRegistry.registerExporter(exporterDescriptor)
 *   widgetRegistry.registerAgentSkill(agentDescriptor)
 */

import type { Component } from "vue";
import type { DashboardWidgetDescriptor } from "./sidebar";
import type { ImporterDescriptor, ImporterSurface } from "./importer";
import type { ExporterDescriptor, ExporterSurface } from "./exporter";
import type { AgentSkillDescriptor, AgentSkillSurface } from "./agent";
import type { PreviewLauncherDescriptor, PreviewLauncherSurface } from "./preview";

// ---------------------------------------------------------------------------
// Registry interface
// ---------------------------------------------------------------------------

export interface DescriptorRegistry {
  registerWidget(descriptor: DashboardWidgetDescriptor): void;
  getWidget(key: string): DashboardWidgetDescriptor | undefined;
  getWidgetComponent(key: string): Component | undefined;
  getAllWidgets(): DashboardWidgetDescriptor[];

  registerImporter(descriptor: ImporterDescriptor): void;
  getImporters(surface: ImporterSurface): ImporterDescriptor[];

  registerExporter(descriptor: ExporterDescriptor): void;
  getExporters(surface: ExporterSurface): ExporterDescriptor[];

  registerAgentSkill(descriptor: AgentSkillDescriptor): void;
  getAgentSkills(surface: AgentSkillSurface): AgentSkillDescriptor[];
  getAgentSkillByToolName(toolName: string): AgentSkillDescriptor | undefined;

  registerPreviewLauncher(descriptor: PreviewLauncherDescriptor): void;
  getPreviewLaunchers(surface: PreviewLauncherSurface): PreviewLauncherDescriptor[];
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

export function createDescriptorRegistry(): DescriptorRegistry {
  const widgetMap = new Map<string, DashboardWidgetDescriptor>();
  const importers: ImporterDescriptor[] = [];
  const exporters: ExporterDescriptor[] = [];
  const agentSkills = new Map<string, AgentSkillDescriptor>();
  const previewLaunchers: PreviewLauncherDescriptor[] = [];

  return {
    registerWidget(descriptor) {
      if (widgetMap.has(descriptor.key)) {
        console.warn(
          `[widget-registry] Sidebar widget "${descriptor.key}" is already registered. Overwriting.`,
        );
      }
      widgetMap.set(descriptor.key, descriptor);
    },

    getWidget(key) {
      return widgetMap.get(key);
    },

    getWidgetComponent(key) {
      return widgetMap.get(key)?.component;
    },

    getAllWidgets() {
      return [...widgetMap.values()];
    },

    registerImporter(descriptor) {
      const existing = importers.findIndex((d) => d.id === descriptor.id);
      if (existing !== -1) {
        console.warn(
          `[widget-registry] Importer "${descriptor.id}" is already registered. Overwriting.`,
        );
        importers.splice(existing, 1, descriptor);
      } else {
        importers.push(descriptor);
      }
    },

    getImporters(surface) {
      return importers.filter((d) => d.surfaces.includes(surface));
    },

    registerExporter(descriptor) {
      const existing = exporters.findIndex((d) => d.id === descriptor.id);
      if (existing !== -1) {
        console.warn(
          `[widget-registry] Exporter "${descriptor.id}" is already registered. Overwriting.`,
        );
        exporters.splice(existing, 1, descriptor);
      } else {
        exporters.push(descriptor);
      }
    },

    getExporters(surface) {
      return exporters.filter((d) => d.surfaces.includes(surface));
    },

    registerAgentSkill(descriptor) {
      if (agentSkills.has(descriptor.toolName)) {
        console.warn(
          `[widget-registry] Agent skill "${descriptor.toolName}" is already registered. Overwriting.`,
        );
      }
      agentSkills.set(descriptor.toolName, descriptor);
    },

    getAgentSkills(surface) {
      return [...agentSkills.values()].filter((d) =>
        d.surfaces.includes(surface),
      );
    },

    getAgentSkillByToolName(toolName) {
      return agentSkills.get(toolName);
    },

    registerPreviewLauncher(descriptor) {
      const existing = previewLaunchers.findIndex((d) => d.id === descriptor.id);
      if (existing !== -1) {
        console.warn(
          `[widget-registry] Preview launcher "${descriptor.id}" is already registered. Overwriting.`,
        );
        previewLaunchers.splice(existing, 1, descriptor);
      } else {
        previewLaunchers.push(descriptor);
      }
    },

    getPreviewLaunchers(surface) {
      return previewLaunchers.filter((d) => d.surfaces.includes(surface));
    },
  };
}
