export const GRAY_LUT_OPTIONS = [
  { label: "Grayscale", value: "gray" },
  { label: "Inverted grayscale", value: "gray-inverted" },
  { label: "Viridis", value: "viridis" },
  { label: "Inferno", value: "inferno" },
  { label: "Turbo", value: "turbo" },
] as const;

export type GrayLUT = (typeof GRAY_LUT_OPTIONS)[number]["value"];

export interface ScGalleryToneMapping {
  enabled: boolean;
  lut: GrayLUT;
  zMin: number;
  zMax: number;
}

export const DEFAULT_SC_GALLERY_TONE_MAPPING: ScGalleryToneMapping = {
  enabled: false,
  lut: "gray",
  zMin: 0,
  zMax: 1,
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
    settings.zMin < settings.zMax
  );
}

export function appendGrayMappingQuery(
  params: URLSearchParams,
  settings: ScGalleryToneMapping,
): void {
  if (!settings.enabled) return;
  if (!isValidGrayWindow(settings)) {
    throw new RangeError("Gray mapping zlims must satisfy 0 <= zMin < zMax <= 1");
  }
  params.set("gray_lut", settings.lut);
  params.set("z_min", String(settings.zMin));
  params.set("z_max", String(settings.zMax));
}

export function colorBarBackground(lut: GrayLUT): string {
  return `linear-gradient(90deg, ${GRAY_LUT_STOPS[lut].join(", ")})`;
}

export function nativeGrayWindow(
  settings: Pick<ScGalleryToneMapping, "zMin" | "zMax">,
  bitDepth: 8 | 16,
): { min: number; max: number } {
  const maximum = bitDepth === 8 ? 255 : 65535;
  return {
    min: Math.round(settings.zMin * maximum),
    max: Math.round(settings.zMax * maximum),
  };
}
