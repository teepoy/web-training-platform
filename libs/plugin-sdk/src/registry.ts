/**
 * @platform/plugin-sdk — Plugin registry
 *
 * The registry is a singleton created once in apps/web/src/core/registry.ts
 * and populated in apps/web/src/plugins/index.ts before app mount.
 *
 * Plugin modules export descriptors created with define*Plugin helpers.
 * The app registration barrel imports those descriptors and calls:
 *   pluginRegistry.registerSidebarWidget(sidebarDescriptor)
 *   pluginRegistry.registerImporter(importDescriptor)
 *   pluginRegistry.registerExporter(exportDescriptor)
 *   pluginRegistry.registerAgentSkill(agentDescriptor)
 */

import type { Component } from "vue";
import type { SidebarPluginDescriptor } from "./sidebar";
import type { ImportPluginDescriptor, ImportPluginSurface } from "./importer";
import type { ExportPluginDescriptor, ExportPluginSurface } from "./exporter";
import type { AgentSkillDescriptor, AgentSkillSurface } from "./agent";

// ---------------------------------------------------------------------------
// Registry interface
// ---------------------------------------------------------------------------

export interface PluginRegistry {
  // --- Sidebar widgets ---
  registerSidebarWidget(descriptor: SidebarPluginDescriptor): void;
  getSidebarWidget(key: string): SidebarPluginDescriptor | undefined;
  getSidebarComponent(key: string): Component | undefined;
  getAllSidebarWidgets(): SidebarPluginDescriptor[];

  // --- Importers ---
  registerImporter(descriptor: ImportPluginDescriptor): void;
  getImporters(surface: ImportPluginSurface): ImportPluginDescriptor[];

  // --- Exporters ---
  registerExporter(descriptor: ExportPluginDescriptor): void;
  getExporters(surface: ExportPluginSurface): ExportPluginDescriptor[];

  // --- Agent skills ---
  registerAgentSkill(descriptor: AgentSkillDescriptor): void;
  getAgentSkills(surface: AgentSkillSurface): AgentSkillDescriptor[];
  getAgentSkillByToolName(toolName: string): AgentSkillDescriptor | undefined;
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

export function createPluginRegistry(): PluginRegistry {
  const sidebarWidgets = new Map<string, SidebarPluginDescriptor>();
  const importers: ImportPluginDescriptor[] = [];
  const exporters: ExportPluginDescriptor[] = [];
  const agentSkills = new Map<string, AgentSkillDescriptor>();

  return {
    // --- Sidebar widgets ---

    registerSidebarWidget(descriptor) {
      if (sidebarWidgets.has(descriptor.key)) {
        console.warn(
          `[plugin-registry] Sidebar widget "${descriptor.key}" is already registered. Overwriting.`,
        );
      }
      sidebarWidgets.set(descriptor.key, descriptor);
    },

    getSidebarWidget(key) {
      return sidebarWidgets.get(key);
    },

    getSidebarComponent(key) {
      return sidebarWidgets.get(key)?.component;
    },

    getAllSidebarWidgets() {
      return [...sidebarWidgets.values()];
    },

    // --- Importers ---

    registerImporter(descriptor) {
      const existing = importers.findIndex((d) => d.id === descriptor.id);
      if (existing !== -1) {
        console.warn(
          `[plugin-registry] Importer "${descriptor.id}" is already registered. Overwriting.`,
        );
        importers.splice(existing, 1, descriptor);
      } else {
        importers.push(descriptor);
      }
    },

    getImporters(surface) {
      return importers.filter((d) => d.surfaces.includes(surface));
    },

    // --- Exporters ---

    registerExporter(descriptor) {
      const existing = exporters.findIndex((d) => d.id === descriptor.id);
      if (existing !== -1) {
        console.warn(
          `[plugin-registry] Exporter "${descriptor.id}" is already registered. Overwriting.`,
        );
        exporters.splice(existing, 1, descriptor);
      } else {
        exporters.push(descriptor);
      }
    },

    getExporters(surface) {
      return exporters.filter((d) => d.surfaces.includes(surface));
    },

    // --- Agent skills ---

    registerAgentSkill(descriptor) {
      if (agentSkills.has(descriptor.toolName)) {
        console.warn(
          `[plugin-registry] Agent skill "${descriptor.toolName}" is already registered. Overwriting.`,
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
  };
}
