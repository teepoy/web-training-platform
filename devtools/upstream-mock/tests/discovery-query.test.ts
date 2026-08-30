import { describe, expect, it } from "vitest";

import { buildInspectionDiscoveryQuery } from "../src/server/discovery-query";

describe("inspection discovery query", () => {
  it("uses the complete publication key as a strict replay-safe cursor", () => {
    const publishedFrom = new Date("2026-08-30T00:00:00Z");
    const publishedUntil = new Date("2026-08-30T02:00:00Z");
    const afterPublishedAt = new Date("2026-08-30T01:00:00Z");
    const afterInspectionTime = new Date("2026-08-01T08:00:00Z");
    const query = buildInspectionDiscoveryQuery({
      order: "publication",
      pageSize: 256,
      publishedFrom,
      publishedUntil,
      afterPublishedAt,
      afterInspectionTime,
      afterWaferKey: 7,
    });

    expect(query.text).toContain("(i.published_at, i.inspection_time, i.wafer_key) > ($3, $4, $5)");
    expect(query.text).toContain("ORDER BY i.published_at, i.inspection_time, i.wafer_key");
    expect(query.text).not.toContain("OFFSET");
    expect(query.values).toEqual([
      publishedFrom,
      publishedUntil,
      afterPublishedAt,
      afterInspectionTime,
      7,
      256,
    ]);
  });

  it("uses canonical inspection identity for independent backfill pages", () => {
    const query = buildInspectionDiscoveryQuery({
      order: "primary_key",
      pageSize: 64,
      startTime: new Date("2026-08-01T00:00:00Z"),
      endTime: new Date("2026-09-01T00:00:00Z"),
      afterInspectionTime: new Date("2026-08-15T00:00:00Z"),
      afterWaferKey: 9,
    });

    expect(query.text).toContain("(i.inspection_time, i.wafer_key) > ($3, $4)");
    expect(query.text).toContain("ORDER BY i.inspection_time, i.wafer_key");
    expect(query.text).not.toContain("OFFSET");
  });
});
