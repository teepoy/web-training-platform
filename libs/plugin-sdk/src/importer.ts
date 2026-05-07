/**
 * @platform/plugin-sdk — Import plugin contracts
 *
 * An import plugin provides a Vue UI component for a specific data import workflow.
 * The component is mounted inside a modal by the host view when the user selects
 * this importer from the import dropdown.
 *
 * Backend access is component-owned. Simple plugins can call existing API client
 * methods directly; custom backend plugins must expose their own typed client
 * helpers and register the FastAPI router in apps/api/app/plugins/registry.py.
 *
 * Component required props: ImportPluginRequiredProps
 * The component signals completion by calling props.onComplete() or props.onCancel().
 */

import type { Component } from "vue";

// ---------------------------------------------------------------------------
// Surface — which host views this importer appears in
// ---------------------------------------------------------------------------

export type ImportPluginSurface = "dataset" | "preview";

// ---------------------------------------------------------------------------
// Plugin descriptor
// ---------------------------------------------------------------------------

export interface ImportPluginDescriptor {
  /**
   * Unique plugin ID.
   * Convention: kebab-case, e.g. "huggingface-importer"
   */
  id: string;
  /** Human-readable label shown in the import dropdown. */
  label: string;
  /** Short description shown as dropdown item subtitle. */
  description?: string;
  /** Which surfaces this importer appears on. */
  surfaces: ImportPluginSurface[];
  /** The Vue component that renders the import workflow UI. */
  component: Component;
}

// ---------------------------------------------------------------------------
// Props that every import plugin component must accept
// ---------------------------------------------------------------------------

/**
 * Every import plugin component must declare these props with defineProps<>.
 *
 * Usage in your .vue file:
 *   const props = defineProps<ImportPluginRequiredProps>()
 */
export interface ImportPluginRequiredProps {
  /** Target dataset (or preview session) ID. */
  datasetId: string;
  /** Call when import is complete (host closes the modal and refreshes data). */
  onComplete: (result?: ImportPluginResult) => void;
  /** Call when the user cancels (host closes the modal). */
  onCancel: () => void;
}

export interface ImportPluginResult {
  imported: number;
  failed: number;
  message?: string;
}

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

export function defineImportPlugin(
  descriptor: ImportPluginDescriptor,
): ImportPluginDescriptor {
  if (!descriptor.id || descriptor.id.trim() === "") {
    throw new Error("[plugin-sdk] defineImportPlugin: id must not be empty");
  }
  if (!descriptor.label || descriptor.label.trim() === "") {
    throw new Error(
      `[plugin-sdk] defineImportPlugin(${descriptor.id}): label must not be empty`,
    );
  }
  if (!descriptor.component) {
    throw new Error(
      `[plugin-sdk] defineImportPlugin(${descriptor.id}): component must be provided`,
    );
  }
  if (descriptor.surfaces.length === 0) {
    throw new Error(
      `[plugin-sdk] defineImportPlugin(${descriptor.id}): surfaces must not be empty`,
    );
  }
  return descriptor;
}
