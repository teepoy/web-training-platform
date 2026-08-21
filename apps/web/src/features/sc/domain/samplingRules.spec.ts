import { describe, expect, it } from "vitest";
import {
  createDefaultScAnnotationSamplingProgram,
  createDefaultScReviewSamplingProgram,
  createDefaultScSamplingRule,
  SC_REVIEW_SAMPLING_RULE_CATALOG,
  scSamplingProgramError,
  scSamplingRequiredFields,
} from "./samplingRules";

describe("SC review sampling rules", () => {
  it("declares the same seventeen product rules and starts with a per-Wafer cap", () => {
    expect(SC_REVIEW_SAMPLING_RULE_CATALOG.map((item) => item.id)).toEqual([
      "cluster_percentage",
      "repeater_percentage",
      "random_percentage",
      "exclude_class_codes",
      "per_die_limit",
      "cluster_count",
      "repeater_count",
      "random_count",
      "per_cluster_limit",
      "per_repeater_limit",
      "per_wafer_limit",
      "require_image",
      "size_range",
      "include_class_codes",
      "large_defect_percentage",
      "large_defect_count",
      "final_class_distribution",
    ]);

    const program = createDefaultScAnnotationSamplingProgram();
    expect(program.extraFilterEnabled).toBe(true);
    expect(program.rules).toEqual([
      { type: "per_die_limit", limit: 10 },
      { type: "per_wafer_limit", limit: 200 },
    ]);
    expect(scSamplingProgramError(program)).toBeNull();

    const reviewProgram = createDefaultScReviewSamplingProgram();
    expect(reviewProgram.extraFilterEnabled).toBe(true);
    expect(reviewProgram.rules).toEqual([{ type: "per_wafer_limit", limit: 100 }]);
    expect(scSamplingProgramError(reviewProgram)).toBeNull();
  });

  it("uses floor rounding for every percentage rule", () => {
    expect(createDefaultScSamplingRule("cluster_percentage")).toMatchObject({ rounding: "floor" });
    expect(createDefaultScSamplingRule("repeater_percentage")).toMatchObject({ rounding: "floor" });
    expect(createDefaultScSamplingRule("random_percentage")).toMatchObject({ rounding: "floor" });
    expect(createDefaultScSamplingRule("large_defect_percentage")).toMatchObject({
      rounding: "floor",
    });
  });

  it("derives every source column required by a combined program", () => {
    const program = createDefaultScAnnotationSamplingProgram();
    program.rules = [
      { type: "cluster_percentage", percentage: 10, rounding: "floor" },
      { type: "repeater_count", count: 20 },
      { type: "per_die_limit", limit: 3 },
      { type: "require_image" },
      { type: "size_range", sizeField: "area", minimum: 2, maximum: 20 },
      {
        type: "final_class_distribution",
        count: 10,
        targets: [
          { value: "Scratch", percentage: 60 },
          { value: "__unclassified__", percentage: 40 },
        ],
      },
    ];

    expect([...scSamplingRequiredFields(program)].sort()).toEqual(
      [
        "area",
        "cluster_id",
        "final_class",
        "images",
        "index_x",
        "index_y",
        "inspection_time",
        "map_id",
        "repeater_id",
        "wafer_key",
      ].sort(),
    );
    expect(scSamplingProgramError(program)).toBeNull();
  });

  it("rejects duplicate rules and invalid final-class distributions", () => {
    const program = createDefaultScAnnotationSamplingProgram();
    program.rules = [
      { type: "random_count", count: 10 },
      { type: "random_count", count: 20 },
    ];
    expect(scSamplingProgramError(program)).toContain("once");

    program.rules = [
      {
        type: "final_class_distribution",
        count: 10,
        targets: [
          { value: "Scratch", percentage: 60 },
          { value: "Particle", percentage: 30 },
        ],
      },
    ];
    expect(scSamplingProgramError(program)).toContain("100%");
  });
});
