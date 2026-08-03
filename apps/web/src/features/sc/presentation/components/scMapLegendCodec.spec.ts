import { describe, expect, it } from "vitest";
import {
  encodeLegendColorMap,
  encodeLegendKey,
  normalizeLegendKey,
} from "@platform/sc-map-element";

describe("map legend key codec", () => {
  it("encodes arbitrary string labels without numeric coercion", () => {
    const codes = new Map<string, number>();
    const keys: string[] = [];

    expect(encodeLegendKey("Scratch", codes, keys)).toBe(0);
    expect(encodeLegendKey("Particle", codes, keys)).toBe(1);
    expect(encodeLegendKey("Scratch", codes, keys)).toBe(0);
    expect(keys).toEqual(["Scratch", "Particle"]);
    expect(encodeLegendColorMap({ Scratch: "#ff0000", Particle: "#00ff00" }, keys)).toEqual({
      "0": "#ff0000",
      "1": "#00ff00",
    });
  });

  it("normalizes missing keys by derived field", () => {
    expect(normalizeLegendKey("annotation_label", null)).toBe("__unlabeled__");
    expect(normalizeLegendKey("prediction_label", null)).toBe("__no_prediction__");
    expect(normalizeLegendKey("final_class", null)).toBe("__unclassified__");
  });
});
