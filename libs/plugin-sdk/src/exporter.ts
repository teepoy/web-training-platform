/**
 * @platform/plugin-sdk — Export plugin contracts
 *
 * An export plugin provides a Vue UI component for a specific data export workflow.
 * The component is mounted inside a panel or modal by the host view when the user
 * selects this exporter from the export dropdown.
 *
 * Backend access is component-owned. Simple plugins can call existing API client
 * methods directly; custom backend plugins must expose their own typed client
 * helpers and register the FastAPI router in apps/api/app/plugins/registry.py.
 */

import type { Component } from "vue";

export type ExportPluginSurface = "dataset" | "preview";

export interface ExportPluginDescriptor {
  id: string;
  label: string;
  description?: string;
  icon?: string;
  surfaces: ExportPluginSurface[];
  component: Component;
}

/**
 * Every export plugin component must declare these props with defineProps<>.
 */
export interface ExportPluginRequiredProps {
  datasetId: string;
  onComplete: (result?: ExportPluginResult) => void;
  onCancel: () => void;
}

export interface ExportPluginResult {
  format?: string;
  url?: string;
  message?: string;
}

export function defineExportPlugin(
  descriptor: ExportPluginDescriptor,
): ExportPluginDescriptor {
  if (!descriptor.id || descriptor.id.trim() === "") {
    throw new Error("[plugin-sdk] defineExportPlugin: id must not be empty");
  }
  if (!descriptor.label || descriptor.label.trim() === "") {
    throw new Error(
      `[plugin-sdk] defineExportPlugin(${descriptor.id}): label must not be empty`,
    );
  }
  if (!descriptor.component) {
    throw new Error(
      `[plugin-sdk] defineExportPlugin(${descriptor.id}): component must be provided`,
    );
  }
  if (descriptor.surfaces.length === 0) {
    throw new Error(
      `[plugin-sdk] defineExportPlugin(${descriptor.id}): surfaces must not be empty`,
    );
  }
  return descriptor;
}
