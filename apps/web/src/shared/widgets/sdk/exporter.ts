/**
 * @/shared/widgets/sdk — Export plugin contracts
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

export type ExporterSurface = "dataset" | "annotation" | "model" | "prediction" | "preview";

export interface ExporterDescriptor {
  id: string;
  label: string;
  labelKey?: string;
  description?: string;
  descriptionKey?: string;
  icon?: string;
  surfaces: ExporterSurface[];
  component: Component;
}

/**
 * Every export plugin component must declare these props with defineProps<>.
 */
export interface ExporterProps {
  datasetId: string;
  resourceId?: string;
  onComplete: (result?: ExporterResult) => void;
  onCancel: () => void;
}

export interface ExporterResult {
  format?: string;
  url?: string;
  message?: string;
}

export function defineExporter(descriptor: ExporterDescriptor): ExporterDescriptor {
  if (!descriptor.id || descriptor.id.trim() === "") {
    throw new Error("[widget-sdk] defineExporter: id must not be empty");
  }
  if (!descriptor.label || descriptor.label.trim() === "") {
    throw new Error(`[widget-sdk] defineExporter(${descriptor.id}): label must not be empty`);
  }
  if (!descriptor.component) {
    throw new Error(`[widget-sdk] defineExporter(${descriptor.id}): component must be provided`);
  }
  if (descriptor.surfaces.length === 0) {
    throw new Error(`[widget-sdk] defineExporter(${descriptor.id}): surfaces must not be empty`);
  }
  return descriptor;
}
