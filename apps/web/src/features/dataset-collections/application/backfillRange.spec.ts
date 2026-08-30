import { describe, expect, it } from "vitest";
import {
  datePickerWallTimeToUtcIso,
  isValidTimeZone,
  resolveBackfillRange,
  supportedTimeZoneOptions,
} from "./backfillRange";

describe("Collection membership Backfill range", () => {
  it("interprets date-picker wall time in the selected IANA timezone", () => {
    const wallTime = new Date(2026, 0, 15, 8, 30, 0).getTime();

    expect(datePickerWallTimeToUtcIso(wallTime, "Asia/Shanghai")).toBe("2026-01-15T00:30:00.000Z");
    expect(datePickerWallTimeToUtcIso(wallTime, "America/New_York")).toBe(
      "2026-01-15T13:30:00.000Z",
    );
  });

  it("requires an ordered range and a valid timezone", () => {
    expect(isValidTimeZone("Asia/Shanghai")).toBe(true);
    expect(isValidTimeZone("Not/AZone")).toBe(false);
    expect(
      resolveBackfillRange({ startAt: 200, endAt: 100, timezone: "Asia/Shanghai" }),
    ).toBeNull();
    expect(resolveBackfillRange({ startAt: 100, endAt: 200, timezone: "Not/AZone" })).toBeNull();
  });

  it("always offers UTC as a timezone option", () => {
    expect(supportedTimeZoneOptions()).toContainEqual({ label: "UTC", value: "UTC" });
  });
});
