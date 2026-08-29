import { afterEach, describe, expect, it } from "vitest";
import { setAppLocale } from "@/app/i18n";
import {
  formatDateTime,
  formatFileSize,
  formatNumber,
  formatPercent,
  formatRelativeTime,
} from "./format";

describe("locale-aware formatting", () => {
  afterEach(() => setAppLocale("en-US", false));

  it("uses the active application locale", () => {
    setAppLocale("en-US", false);
    expect(formatNumber(12_345.6)).toBe("12,345.6");
    expect(formatPercent(0.125)).toBe("12.5%");
    expect(formatFileSize(1536)).toBe("1.5 KB");

    setAppLocale("zh-CN", false);
    expect(formatNumber(12_345.6)).toBe("12,345.6");
    expect(formatRelativeTime("2026-08-28T00:00:00Z", Date.parse("2026-08-29T00:00:00Z"))).toBe(
      "昨天",
    );
    expect(formatDateTime("2026-08-29T08:00:00Z")).not.toBe("");
  });
});
