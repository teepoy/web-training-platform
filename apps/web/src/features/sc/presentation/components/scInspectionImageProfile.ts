import { scInspectionImageProfileUrl } from "@/features/sc/domain/models";
import { requestData } from "@/shared/api/client";

export type ScPatchImageType = "Defective" | "Reference" | "Difference" | "Mask";

export interface ScInspectionImagePatch {
  image_type: ScPatchImageType;
  image_id: number | null;
  bit_depth: 8 | 12 | 16;
  z_min: number;
  z_max: number;
}

export interface ScInspectionImageProfile {
  inspection_time: string;
  wafer_key: number;
  reference_count: number;
  difference_count: number;
  mask_count: number;
  patches: ScInspectionImagePatch[];
}

export interface ScPatchImageDescriptor extends ScInspectionImagePatch {
  key: string;
  label: string;
  spriteToken: string;
}

export interface ScPatchGroupProfile {
  bitDepth: 8 | 12 | 16;
  zMin: number;
  zMax: number;
  patches: ScPatchImageDescriptor[];
}

const SPRITE_PREFIX: Record<ScPatchImageType, string> = {
  Defective: "patchDefective",
  Reference: "patchReference",
  Difference: "patchDifference",
  Mask: "patchMask",
};

export async function loadScInspectionImageProfile(
  inspectionTime: string,
  waferKey: number,
  signal?: AbortSignal,
): Promise<ScInspectionImageProfile> {
  const profile = await requestData<ScInspectionImageProfile>(
    scInspectionImageProfileUrl(inspectionTime, waferKey),
    { signal, cache: "no-store" },
    120_000,
  );
  validateProfile(profile);
  return profile;
}

export function patchDescriptors(profile: ScInspectionImageProfile): ScPatchImageDescriptor[] {
  return profile.patches.map((patch) => {
    const suffix = patch.image_id == null ? "" : `:${patch.image_id}`;
    const instance = patch.image_id == null ? "" : ` ${patch.image_id + 1}`;
    return {
      ...patch,
      key: `${patch.image_type}${suffix}`,
      label: `${patch.image_type}${instance}`,
      spriteToken: `${SPRITE_PREFIX[patch.image_type]}${suffix}`,
    };
  });
}

export function groupProfile(
  patches: ScPatchImageDescriptor[],
  group: "defective_reference" | "difference",
): ScPatchGroupProfile | null {
  const selected = patches.filter((patch) =>
    group === "difference"
      ? patch.image_type === "Difference"
      : patch.image_type === "Defective" || patch.image_type === "Reference",
  );
  if (selected.length === 0) return null;
  const bitDepth = Math.max(...selected.map((patch) => patch.bit_depth)) as 8 | 12 | 16;
  const normalizedMinimum = Math.min(
    ...selected.map((patch) => patch.z_min / nativeMaximum(patch.bit_depth)),
  );
  const normalizedMaximum = Math.max(
    ...selected.map((patch) => patch.z_max / nativeMaximum(patch.bit_depth)),
  );
  return {
    bitDepth,
    zMin: clampWindowValue(normalizedMinimum),
    zMax: clampWindowValue(normalizedMaximum),
    patches: selected,
  };
}

export function nativeMaximum(bitDepth: 8 | 12 | 16): number {
  return 2 ** bitDepth - 1;
}

function clampWindowValue(value: number): number {
  return Math.min(1, Math.max(0, value));
}

function validateProfile(profile: ScInspectionImageProfile): void {
  if (!profile || !Array.isArray(profile.patches)) {
    throw new TypeError("Inspection image profile must contain patches");
  }
  for (const patch of profile.patches) {
    if (!["Defective", "Reference", "Difference", "Mask"].includes(patch.image_type)) {
      throw new TypeError(`Unsupported patch image type ${String(patch.image_type)}`);
    }
    if (![8, 12, 16].includes(patch.bit_depth)) {
      throw new TypeError(`Unsupported patch bit depth ${String(patch.bit_depth)}`);
    }
    const maximum = nativeMaximum(patch.bit_depth);
    if (
      !Number.isInteger(patch.z_min) ||
      !Number.isInteger(patch.z_max) ||
      patch.z_min < 0 ||
      patch.z_max > maximum ||
      patch.z_min > patch.z_max
    ) {
      throw new TypeError(`Invalid native grayscale range for ${patch.image_type}`);
    }
  }
}
