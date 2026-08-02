import { describe, expect, it } from "vitest";
import {
  isScMissingFilterValue,
  scMissingFilterOption,
  splitScSetFilterValues,
} from "./missingFilterValue";

describe("SC missing filter values", () => {
  it("uses field-specific labels and sentinel values", () => {
    expect(scMissingFilterOption("annotation_label")).toEqual({
      value: "__unlabeled__",
      label: "Unlabeled",
    });
    expect(scMissingFilterOption("prediction_label")).toEqual({
      value: "__no_prediction__",
      label: "No Prediction",
    });
    expect(scMissingFilterOption("final_class")).toEqual({
      value: "__unclassified__",
      label: "Unclassified",
    });
  });

  it("separates missing selections from concrete values", () => {
    expect(splitScSetFilterValues("prediction_label", ["Scratch", "__no_prediction__"])).toEqual({
      values: ["Scratch"],
      includeMissing: true,
    });
    expect(isScMissingFilterValue("prediction_label", "__unlabeled__")).toBe(false);
  });
});
