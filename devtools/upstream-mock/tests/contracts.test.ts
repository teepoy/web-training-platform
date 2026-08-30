import { describe, expect, it } from "vitest";

import {
  appendRecordsSchema,
  createInspectionSchema,
  showcaseScenarioSchema,
  updateInspectionSchema,
} from "../src/server/contracts";

const inspection = {
  wafer_key: 7,
  inspection_time: "2026-08-30T01:02:00+08:00",
  lot_id: "LOT-1",
  wafer_id: "WAFER-1",
  layer_id: "LAYER-1",
  device: "DEVICE-1",
  inspect_equip_id: "EQP-1",
  recipe_key: 11,
  recipe_id: "RECIPE-1",
  origin_index_x: 0,
  origin_index_y: 0,
  center_x: 1000,
  center_y: 1000,
  origin_x: 0,
  origin_y: 0,
  die_size_x: 20,
  die_size_y: 30,
  defects: [],
  review_images: [],
  patch_archives: [],
};

describe("upstream mock contracts", () => {
  it("accepts the compatibility create shape and normalizes timestamps", () => {
    const value = createInspectionSchema.parse(inspection);

    expect(value.inspection_time).toEqual(new Date("2026-08-29T17:02:00.000Z"));
  });

  it("rejects empty appends and unknown fields", () => {
    expect(() =>
      appendRecordsSchema.parse({
        wafer_key: 7,
        inspection_time: "2026-08-30T01:02:00+08:00",
        defects: [],
        review_images: [],
        patch_archives: [],
      }),
    ).toThrow("at least one child record is required");
    expect(() => createInspectionSchema.parse({ ...inspection, hidden_seed_mode: true })).toThrow();
  });

  it("requires at least one explicit source change", () => {
    expect(() =>
      updateInspectionSchema.parse({
        wafer_key: 7,
        inspection_time: "2026-08-30T01:02:00+08:00",
        changed_at: "2026-08-30T01:03:00+08:00",
      }),
    ).toThrow("at least one mutable field is required");
  });

  it("keeps scenario quantities explicit", () => {
    const scenario = showcaseScenarioSchema.parse({
      inspection_time: "2026-08-30T00:00:00Z",
      published_at: "2026-08-30T00:05:00Z",
      total_defects: 2500,
      imaged_defects: 16,
      images_per_defect: 5,
      gallery_defects: 64,
      gallery_imaged_defects: 8,
      defects_per_archive: 500,
      append_batch_size: 500,
    });

    expect(scenario.total_defects).toBe(2500);
    expect(scenario.published_at).toBeInstanceOf(Date);
  });
});
