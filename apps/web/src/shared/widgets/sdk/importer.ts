/**
 * @/shared/widgets/sdk — Import plugin contracts
 *
 * An import plugin provides a Vue UI component for a specific data import workflow.
 * The component is mounted inside a modal by the host view when the user selects
 * this importer from the import dropdown.
 *
 * Backend access is component-owned. Simple plugins can call existing API client
 * methods directly; custom backend plugins must expose their own typed client
 * helpers and register the FastAPI router in apps/api/app/plugins/registry.py.
 *
 * Component required props: ImporterProps
 * The component signals completion by calling props.onComplete() or props.onCancel().
 */

import type { Component } from "vue";

// ---------------------------------------------------------------------------
// Surface — which host views this importer appears in
// ---------------------------------------------------------------------------

export type ImporterSurface = "dataset" | "annotation" | "model" | "preview";

// ---------------------------------------------------------------------------
// Plugin descriptor
// ---------------------------------------------------------------------------

export interface ImporterDescriptor {
  id: string;
  label: string;
  labelKey?: string;
  description?: string;
  descriptionKey?: string;
  icon?: string;
  surfaces: ImporterSurface[];
  component: Component;
}

// ---------------------------------------------------------------------------
// Props that every import plugin component must accept
// ---------------------------------------------------------------------------

/**
 * Every import plugin component must declare these props with defineProps<>.
 *
 * Usage in your .vue file:
 *   const props = defineProps<ImporterProps>()
 */
export interface ImporterProps {
  /** Target dataset (or preview session) ID. */
  datasetId: string;
  /** Generic target resource ID for non-Dataset transfer surfaces. */
  resourceId?: string;
  /** Call when import is complete (host closes the modal and refreshes data). */
  onComplete: (result?: ImporterResult) => void;
  /** Call when the user cancels (host closes the modal). */
  onCancel: () => void;
}

export interface ImporterResult {
  imported: number;
  failed: number;
  message?: string;
}

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

export function defineImporter(descriptor: ImporterDescriptor): ImporterDescriptor {
  if (!descriptor.id || descriptor.id.trim() === "") {
    throw new Error("[widget-sdk] defineImporter: id must not be empty");
  }
  if (!descriptor.label || descriptor.label.trim() === "") {
    throw new Error(`[widget-sdk] defineImporter(${descriptor.id}): label must not be empty`);
  }
  if (!descriptor.component) {
    throw new Error(`[widget-sdk] defineImporter(${descriptor.id}): component must be provided`);
  }
  if (descriptor.surfaces.length === 0) {
    throw new Error(`[widget-sdk] defineImporter(${descriptor.id}): surfaces must not be empty`);
  }
  return descriptor;
}
