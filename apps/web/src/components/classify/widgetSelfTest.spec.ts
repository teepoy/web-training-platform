import { describe, expect, it } from "vitest";
import { SIDEBAR_WIDGETS } from "./sidebarConfig";
import { runSidebarWidgetSelfTest } from "./widgetContract";

describe("sidebar widget author self-tests", () => {
  for (const definition of Object.values(SIDEBAR_WIDGETS)) {
    it(`validates ${definition.key}`, () => {
      const result = runSidebarWidgetSelfTest(definition);

      expect(result.passed).toBe(true);
      expect(result.checks.every((check) => check.passed)).toBe(true);
    });
  }
});
