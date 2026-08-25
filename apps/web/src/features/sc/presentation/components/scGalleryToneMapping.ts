export const GRAY_LUT_OPTIONS = [
  { label: "Grayscale", value: "gray" },
  { label: "Inverted grayscale", value: "gray-inverted" },
  { label: "Viridis", value: "viridis" },
  { label: "Inferno", value: "inferno" },
  { label: "Turbo", value: "turbo" },
] as const;

export type GrayLUT = (typeof GRAY_LUT_OPTIONS)[number]["value"];
export type GrayMappingMode = "global" | "adaptive";

export const GRAY_MAPPING_MODE_OPTIONS = [
  { label: "Global", value: "global" },
  { label: "Adaptive", value: "adaptive" },
] as const;

export interface ScGalleryToneMapping {
  enabled: boolean;
  mode: GrayMappingMode;
  lut: GrayLUT;
  zMin: number;
  zMax: number;
  bitDepth: 8 | 12 | 16;
}

export type ScGalleryToneMappingGroup = "defective_reference" | "difference";

export const DEFAULT_SC_GALLERY_TONE_MAPPING: ScGalleryToneMapping = {
  enabled: false,
  mode: "global",
  lut: "gray",
  zMin: 0,
  zMax: 1,
  bitDepth: 16,
};

export const GRAY_LUT_STOPS: Record<GrayLUT, readonly string[]> = {
  gray: ["#000000", "#ffffff"],
  "gray-inverted": ["#ffffff", "#000000"],
  viridis: ["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"],
  inferno: ["#000004", "#420a68", "#932667", "#dd513a", "#fca50a", "#fcffa4"],
  turbo: ["#30123b", "#4662d7", "#1ae4b6", "#a4fc3c", "#f9ba38", "#e94b18", "#7a0403"],
};

export function isGrayLUT(value: unknown): value is GrayLUT {
  return GRAY_LUT_OPTIONS.some((option) => option.value === value);
}

export function isValidGrayWindow(settings: ScGalleryToneMapping): boolean {
  return (
    Number.isFinite(settings.zMin) &&
    Number.isFinite(settings.zMax) &&
    settings.zMin >= 0 &&
    settings.zMax <= 1 &&
    settings.zMin < settings.zMax &&
    [8, 12, 16].includes(settings.bitDepth)
  );
}

export function appendGrayMappingQuery(
  params: URLSearchParams,
  settings: ScGalleryToneMapping,
  group?: ScGalleryToneMappingGroup,
): void {
  if (!settings.enabled) return;
  if (!isValidGrayWindow(settings)) {
    throw new RangeError("Gray mapping zlims must satisfy 0 <= zMin < zMax <= 1");
  }
  const prefix = group ? `${group}_` : "";
  params.set(`${prefix}gray_mode`, settings.mode);
  params.set(`${prefix}gray_lut`, settings.lut);
  params.set(`${prefix}z_min`, String(settings.zMin));
  params.set(`${prefix}z_max`, String(settings.zMax));
  params.set(`${prefix}bit_depth`, String(settings.bitDepth));
}

export function colorBarBackground(lut: GrayLUT, zMin = 0, zMax = 1): string {
  if (!Number.isFinite(zMin) || !Number.isFinite(zMax) || zMin < 0 || zMax > 1 || zMin >= zMax) {
    throw new RangeError("Color bar window must satisfy 0 <= zMin < zMax <= 1");
  }
  const start = zMin * 100;
  const end = zMax * 100;
  const span = end - start;
  const stops = GRAY_LUT_STOPS[lut].map((color, index, colors) => {
    const position = start + (span * index) / Math.max(1, colors.length - 1);
    return `${color} ${position.toFixed(3)}%`;
  });
  const colors = GRAY_LUT_STOPS[lut];
  const minimum = colors[0];
  const maximum = colors.at(-1);
  return `linear-gradient(90deg, ${minimum} 0%, ${minimum} ${start.toFixed(3)}%, ${stops.join(", ")}, ${maximum} ${end.toFixed(3)}%, ${maximum} 100%)`;
}

export function nativeGrayWindow(
  settings: Pick<ScGalleryToneMapping, "zMin" | "zMax">,
  bitDepth: 8 | 12 | 16,
): { min: number; max: number } {
  const maximum = 2 ** bitDepth - 1;
  return {
    min: Math.round(settings.zMin * maximum),
    max: Math.round(settings.zMax * maximum),
  };
}
