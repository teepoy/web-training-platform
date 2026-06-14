import { describe, expect, it } from "vitest";
import { BROWSER_DASHBOARD_KEY } from "@/shared/widgets/sdk";

describe("widget-sdk BROWSER_DASHBOARD_KEY", () => {
  it("exports BROWSER_DASHBOARD_KEY from widget-sdk", () => {
    expect(BROWSER_DASHBOARD_KEY).toBeDefined();
    expect(typeof BROWSER_DASHBOARD_KEY).toBe("symbol");
  });
});
