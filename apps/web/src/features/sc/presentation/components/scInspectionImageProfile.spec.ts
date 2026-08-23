import { describe, expect, it } from "vitest";
import {
  groupProfile,
  patchDescriptors,
  type ScInspectionImageProfile,
} from "./scInspectionImageProfile";

const profile: ScInspectionImageProfile = {
  inspection_time: "2026-08-23T00:00:00Z",
  wafer_key: 9,
  reference_count: 2,
  difference_count: 2,
  mask_count: 1,
  patches: [
    { image_type: "Defective", image_id: null, bit_depth: 12, z_min: 100, z_max: 3500 },
    { image_type: "Reference", image_id: 0, bit_depth: 12, z_min: 200, z_max: 3000 },
    { image_type: "Reference", image_id: 1, bit_depth: 12, z_min: 300, z_max: 3200 },
    { image_type: "Difference", image_id: 0, bit_depth: 12, z_min: 10, z_max: 1000 },
    { image_type: "Difference", image_id: 1, bit_depth: 12, z_min: 20, z_max: 2000 },
    { image_type: "Mask", image_id: 0, bit_depth: 8, z_min: 0, z_max: 1 },
  ],
};

describe("inspection image profile", () => {
  it("preserves multiple Reference and Difference instances", () => {
    const descriptors = patchDescriptors(profile);
    expect(descriptors.map((item) => item.key)).toEqual([
      "Defective",
      "Reference:0",
      "Reference:1",
      "Difference:0",
      "Difference:1",
      "Mask:0",
    ]);
    expect(descriptors.map((item) => item.spriteToken)).toEqual([
      "patchDefective",
      "patchReference:0",
      "patchReference:1",
      "patchDifference:0",
      "patchDifference:1",
      "patchMask:0",
    ]);
  });

  it("derives the initial normalized window from the native 12-bit ranges", () => {
    const descriptors = patchDescriptors(profile);
    expect(groupProfile(descriptors, "defective_reference")).toMatchObject({
      bitDepth: 12,
      zMin: 100 / 4095,
      zMax: 3500 / 4095,
    });
    expect(groupProfile(descriptors, "difference")).toMatchObject({
      bitDepth: 12,
      zMin: 10 / 4095,
      zMax: 2000 / 4095,
    });
  });

  it.each([
    { bitDepth: 8 as const, maximum: 255 },
    { bitDepth: 16 as const, maximum: 65_535 },
  ])("uses the native $bitDepth-bit domain for gallery groups", ({ bitDepth, maximum }) => {
    const nativeProfile: ScInspectionImageProfile = {
      ...profile,
      patches: profile.patches
        .filter((patch) => patch.image_type !== "Mask")
        .map((patch) => ({ ...patch, bit_depth: bitDepth, z_min: 0, z_max: maximum })),
    };

    expect(groupProfile(patchDescriptors(nativeProfile), "defective_reference")).toMatchObject({
      bitDepth,
      zMin: 0,
      zMax: 1,
    });
    expect(groupProfile(patchDescriptors(nativeProfile), "difference")).toMatchObject({
      bitDepth,
      zMin: 0,
      zMax: 1,
    });
  });
});
