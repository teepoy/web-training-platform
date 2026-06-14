import type { SidebarPanelDescriptor, WaferPoint } from '@/shared/types/components';

export function metadataNumber(
  metadata: Record<string, unknown>,
  key: string,
): number | null {
  const value = metadata[key];
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function metadataString(
  metadata: Record<string, unknown>,
  key: string,
): string | null {
  const value = metadata[key];
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

export function normalizeWaferPoint(point: WaferPoint): WaferPoint | null {
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
