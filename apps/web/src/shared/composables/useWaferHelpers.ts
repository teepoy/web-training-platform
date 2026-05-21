import type { SidebarPanelDescriptor, WaferPoint } from "../types/components";

/**
 * Extract a number from a metadata record by key.
 * Returns null when the value is not a finite number.
 */
export function metadataNumber(
  metadata: Record<string, unknown>,
  key: string,
): number | null {
  const value = metadata[key];
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Extract a non-empty string from a metadata record by key.
 * Returns null when the value is not a non-empty string.
 */
export function metadataString(
  metadata: Record<string, unknown>,
  key: string,
): string | null {
  const value = metadata[key];
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

/**
 * Normalize a raw wafer point so coordinate fields are guaranteed numbers.
 * Points with missing / empty id or invalid (non-finite) x/y are discarded.
 *
 * Byte-for-byte identical to the normalization in ClassifyView and
 * DatasetDetailView — extracted here so every surface shares one
 * implementation.
 */
export function normalizeWaferPoint(
  point: WaferPoint,
): WaferPoint | null {
  if (typeof point.id !== "string" || point.id.trim().length === 0) {
    return null;
  }

  const x = Number(point.x);
  const y = Number(point.y);
  if (!Number.isFinite(x) || !Number.isFinite(y)) {
    return null;
  }

  const value = Number(point.value);

  return {
    id: point.id,
    x,
    y,
    ...(Number.isFinite(value) ? { value } : {}),
  };
}

/**
 * Find the wafer-map panel in a panel array and inject wafer points into
 * `props.data.inline.points`.  When `collectionKey` is supplied it also
 * sets `config.interaction.collection` on the panel so that linked
 * selection/filter intents target the correct surface collection.
 *
 * Collection keys vary per surface:
 *   - "classify-samples"  – ClassifyView
 *   - "browser-items"     – DatasetDetailView, PreviewClassifyView
 */
export function injectWaferPanelData(
  panels: SidebarPanelDescriptor[],
  points: WaferPoint[],
  collectionKey?: string,
): SidebarPanelDescriptor[] {
  return panels.map((panel) => {
    if (panel.id !== "wafer-map") {
      return panel;
    }

    const config =
      (panel.props.config as Record<string, unknown> | undefined) ?? {};
    const interaction =
      (config.interaction as Record<string, unknown> | undefined) ?? {};

    return {
      ...panel,
      props: {
        ...panel.props,
        data: {
          inline: {
            points,
          },
        },
        ...(collectionKey !== undefined
          ? {
              config: {
                ...config,
                interaction: {
                  ...interaction,
                  collection: collectionKey,
                },
              },
            }
          : {}),
      },
    };
  });
}
