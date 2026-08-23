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
  bitDepth: 12,
};

describe("scGalleryToneMapping", () => {
  it("adds an explicit normalized gray mapping contract to sprite URLs", () => {
    const params = new URLSearchParams();
    appendGrayMappingQuery(params, VIRIDIS);

    expect(params.get("gray_lut")).toBe("viridis");
    expect(params.get("z_min")).toBe("0.125");
    expect(params.get("z_max")).toBe("0.875");
    expect(params.get("bit_depth")).toBe("12");
  });

  it("leaves source rendering untouched when mapping is disabled", () => {
    const params = new URLSearchParams();
    appendGrayMappingQuery(params, { ...VIRIDIS, enabled: false });

    expect(params.toString()).toBe("");
  });

  it("projects one normalized window onto both native gray depths", () => {
    expect(nativeGrayWindow(VIRIDIS, 8)).toEqual({ min: 32, max: 223 });
    expect(nativeGrayWindow(VIRIDIS, 12)).toEqual({ min: 512, max: 3583 });
    expect(nativeGrayWindow(VIRIDIS, 16)).toEqual({ min: 8192, max: 57343 });
  });

  it("uses the selected LUT stops for the visible color bar", () => {
    const background = colorBarBackground("viridis");
    expect(background).toContain("linear-gradient");
    expect(background).toContain("#440154");
    expect(background).toContain("#fde725");
  });

  it("names grouped mappings independently", () => {
    const params = new URLSearchParams();
    appendGrayMappingQuery(params, VIRIDIS, "defective_reference");
    appendGrayMappingQuery(params, { ...VIRIDIS, lut: "inferno" }, "difference");

    expect(params.get("defective_reference_gray_lut")).toBe("viridis");
    expect(params.get("difference_gray_lut")).toBe("inferno");
    expect(params.has("gray_lut")).toBe(false);
  });

  it("moves the mapped color region with the selected window", () => {
    const background = colorBarBackground("viridis", 0.25, 0.75);

    expect(background).toContain("#242430) 25.000%");
    expect(background).toContain("#440154 25.000%");
    expect(background).toContain("#fde725 75.000%");
    expect(background).toContain("#242430) 75.000%");
  });
});
