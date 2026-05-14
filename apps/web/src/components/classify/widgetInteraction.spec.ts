import { describe, expect, it } from "vitest";
import { BROWSER_DASHBOARD_KEY } from "@platform/widget-sdk";

describe("widgetContract re-exports", () => {
  it("re-exports BROWSER_DASHBOARD_KEY from widget-sdk", () => {
    expect(BROWSER_DASHBOARD_KEY).toBeDefined();
    expect(typeof BROWSER_DASHBOARD_KEY).toBe("symbol");
  });
});
