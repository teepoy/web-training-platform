import { describe, expect, it } from "vitest";

import { buildMembershipSampleQuery } from "../src/server/membership-sample-query";

describe("membership sample query", () => {
  it("filters by canonical inspection identity and requested defect IDs in PostgreSQL", () => {
    const inspectionTime = new Date("2026-08-30T00:00:00Z");
    const query = buildMembershipSampleQuery({
      inspectionTime,
      waferKey: 7,
      defectIds: [11, 13],
      projection: ["defect_id", "rough_bin"],
    });

    expect(query.text).toContain("JOIN unnest($3::bigint[])");
    expect(query.text).toContain("d.wafer_key = $1 AND d.inspection_time = $2");
    expect(query.text).toContain("d.defect_id AS defect_id");
    expect(query.text).toContain("d.rough_bin AS rough_bin");
    expect(query.text).not.toContain("d.class_number AS class_number");
    expect(query.text).not.toContain("OFFSET");
    expect(query.values).toEqual([7, inspectionTime, [11, 13]]);
  });

  it("rejects unsupported projection names", () => {
    expect(() =>
      buildMembershipSampleQuery({
        inspectionTime: new Date("2026-08-30T00:00:00Z"),
        waferKey: 7,
        defectIds: [11],
        projection: ["not_a_source_column"],
      }),
    ).toThrow("unsupported sample projection");
  });
});
