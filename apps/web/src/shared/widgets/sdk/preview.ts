/**
 * @/shared/widgets/sdk — Preview launcher plugin contracts
 *
 * A preview launcher plugin provides a Vue UI component for creating a
 * preview session from an upstream data source.  The component is mounted
 * inside a modal by the host view when the user selects this launcher from a
 * type-selector grid.
 *
 * Component required props: PreviewLauncherRequiredProps
 * The component signals completion by calling props.onComplete().
 */

import type { Component } from "vue";

// ---------------------------------------------------------------------------
// Surface — which host views this launcher appears in
// ---------------------------------------------------------------------------

export type PreviewLauncherSurface = "dataset-list" | "preview";

// ---------------------------------------------------------------------------
// Plugin descriptor
// ---------------------------------------------------------------------------

export interface PreviewLauncherDescriptor {
  /**
   * Unique plugin ID.
   * Convention: kebab-case, e.g. "upstream-preview"
   */
  id: string;
  /** Human-readable label shown in the type-selector card. */
  label: string;
  /** Short description shown as card subtitle. */
  description?: string;
  /** Optional icon name (Naive UI icon name or emoji). */
  icon?: string;
  /** Which surfaces this launcher appears on. */
  surfaces: PreviewLauncherSurface[];
  /** The Vue component that renders the launcher workflow UI. */
  component: Component;
}

// ---------------------------------------------------------------------------
// Props that every preview launcher component must accept
// ---------------------------------------------------------------------------

/**
 * Every preview launcher component must declare these props with defineProps<>.
 *
 * Usage in your .vue file:
 *   const props = defineProps<PreviewLauncherRequiredProps>()
 */
export interface PreviewLauncherRequiredProps {
  /** Call when preview session is created (host navigates to /preview/:sessionId). */
  onComplete: (result: PreviewLauncherResult) => void;
  /** Call when the user cancels (host closes the modal). */
  onCancel: () => void;
}

export interface PreviewLauncherResult {
  sessionId: string;
  message?: string;
}

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

export function definePreviewLauncher(
  descriptor: PreviewLauncherDescriptor,
): PreviewLauncherDescriptor {
  if (!descriptor.id || descriptor.id.trim() === "") {
    throw new Error("[widget-sdk] definePreviewLauncher: id must not be empty");
  }
  if (!descriptor.label || descriptor.label.trim() === "") {
    throw new Error(
      `[widget-sdk] definePreviewLauncher(${descriptor.id}): label must not be empty`,
    );
  }
  if (!descriptor.component) {
    throw new Error(
      `[widget-sdk] definePreviewLauncher(${descriptor.id}): component must be provided`,
    );
  }
  if (descriptor.surfaces.length === 0) {
    throw new Error(
      `[widget-sdk] definePreviewLauncher(${descriptor.id}): surfaces must not be empty`,
    );
  }
  return descriptor;
}
