import { describe, expect, it } from "vitest";
import {
  appendGrayMappingQuery,
  colorBarBackground,
  nativeGrayWindow,
  type ScGalleryToneMapping,
} from "./scGalleryToneMapping";

const VIRIDIS: ScGalleryToneMapping = {
  enabled: true,
  lut: "viridis",
  zMin: 0.125,
  zMax: 0.875,
};

describe("scGalleryToneMapping", () => {
  it("adds an explicit normalized gray mapping contract to sprite URLs", () => {
    const params = new URLSearchParams();
    appendGrayMappingQuery(params, VIRIDIS);

    expect(params.get("gray_lut")).toBe("viridis");
    expect(params.get("z_min")).toBe("0.125");
    expect(params.get("z_max")).toBe("0.875");
  });

  it("leaves source rendering untouched when mapping is disabled", () => {
    const params = new URLSearchParams();
    appendGrayMappingQuery(params, { ...VIRIDIS, enabled: false });

    expect(params.toString()).toBe("");
  });

  it("projects one normalized window onto both native gray depths", () => {
    expect(nativeGrayWindow(VIRIDIS, 8)).toEqual({ min: 32, max: 223 });
    expect(nativeGrayWindow(VIRIDIS, 16)).toEqual({ min: 8192, max: 57343 });
  });

  it("uses the selected LUT stops for the visible color bar", () => {
    const background = colorBarBackground("viridis");
    expect(background).toContain("linear-gradient");
    expect(background).toContain("#440154");
    expect(background).toContain("#fde725");
  });
});
