import { describe, expect, it } from "vitest";
import "../../plugins/index";
import { pluginRegistry } from "../../core/registry";
import { runSidebarWidgetSelfTest } from "./widgetContract";

describe("sidebar widget author self-tests", () => {
  for (const definition of pluginRegistry.getAllSidebarWidgets()) {
    it(`validates ${definition.key}`, () => {
      const result = runSidebarWidgetSelfTest(definition);

      expect(result.passed).toBe(true);
      expect(result.checks.every((check) => check.passed)).toBe(true);
    });
  }
});
