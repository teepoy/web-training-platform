import { describe, it, expect, vi } from "vitest";
import { defineComponent } from "vue";
import {
  defineDashboardWidget,
  defineImporter,
  defineExporter,
  defineAgentSkill,
  definePreviewLauncher,
  createDescriptorRegistry,
  reduceLabelFilterIntent,
  reduceCollectionIntent,
} from "./index";
import type { SidebarWidgetIntent } from "./sidebar";
import * as widgetSdk from "./index";
import { readFileSync } from "fs";
import { resolve } from "path";

// ---------------------------------------------------------------------------
// Stub component (Vue component without a DOM env)
// ---------------------------------------------------------------------------

const StubComponent = defineComponent({ template: "<div/>" });

// ---------------------------------------------------------------------------
// defineDashboardWidget
// ---------------------------------------------------------------------------

describe("defineDashboardWidget", () => {
  it("returns the descriptor unchanged for a valid input", () => {
    const d = defineDashboardWidget({
      key: "my-widget",
      component: StubComponent,
      contract: {
        displayName: "My Widget",
        description: "Test widget",
        acceptsProps: [],
        capabilities: { reads: [], emits: [] },
        selfTests: [],
      },
    });
    expect(d.key).toBe("my-widget");
  });

  it("throws when key is empty", () => {
    expect(() =>
      defineDashboardWidget({
        key: "",
        component: StubComponent,
        contract: {
          displayName: "X",
          description: "",
          acceptsProps: [],
          capabilities: { reads: [], emits: [] },
          selfTests: [],
        },
      }),
    ).toThrow("key must not be empty");
  });

  it("throws when displayName is empty", () => {
    expect(() =>
      defineDashboardWidget({
        key: "x",
        component: StubComponent,
        contract: {
          displayName: "",
          description: "",
          acceptsProps: [],
          capabilities: { reads: [], emits: [] },
          selfTests: [],
        },
      }),
    ).toThrow("displayName must not be empty");
  });
});

// ---------------------------------------------------------------------------
// defineImporter
// ---------------------------------------------------------------------------

describe("defineImporter", () => {
  it("validates successfully", () => {
    const d = defineImporter({
      id: "csv-importer",
      label: "CSV",
      surfaces: ["dataset"],
      component: StubComponent,
    });
    expect(d.id).toBe("csv-importer");
  });

  it("throws when surfaces is empty", () => {
    expect(() =>
      defineImporter({
        id: "csv-importer",
        label: "CSV",
        surfaces: [],
        component: StubComponent,
      }),
    ).toThrow("surfaces must not be empty");
  });
});

// ---------------------------------------------------------------------------
// defineExporter
// ---------------------------------------------------------------------------

describe("defineExporter", () => {
  it("validates successfully", () => {
    const d = defineExporter({
      id: "csv-exporter",
      label: "CSV Export",
      surfaces: ["dataset"],
      component: StubComponent,
    });
    expect(d.id).toBe("csv-exporter");
  });
});

// ---------------------------------------------------------------------------
// defineAgentSkill
// ---------------------------------------------------------------------------

describe("defineAgentSkill", () => {
  it("validates successfully", () => {
    const d = defineAgentSkill({
      toolName: "search_dataset",
      displayName: "Search Dataset",
      description: "Searches within a dataset.",
      surfaces: ["classify", "dataset"],
    });
    expect(d.toolName).toBe("search_dataset");
  });

  it("throws when toolName is empty", () => {
    expect(() =>
      defineAgentSkill({
        toolName: "",
        displayName: "X",
        description: "",
        surfaces: ["global"],
      }),
    ).toThrow("toolName must not be empty");
  });
});

// ---------------------------------------------------------------------------
// definePreviewLauncher
// ---------------------------------------------------------------------------

describe("definePreviewLauncher", () => {
  it("validates successfully", () => {
    const d = definePreviewLauncher({
      id: "upstream-preview",
      label: "Upstream",
      surfaces: ["preview"],
      component: StubComponent,
    });
    expect(d.id).toBe("upstream-preview");
  });

  it("throws when id is empty", () => {
    expect(() =>
      definePreviewLauncher({
        id: "",
        label: "X",
        surfaces: ["preview"],
        component: StubComponent,
      }),
    ).toThrow("id must not be empty");
  });

  it("throws when surfaces is empty", () => {
    expect(() =>
      definePreviewLauncher({
        id: "test",
        label: "X",
        surfaces: [],
        component: StubComponent,
      }),
    ).toThrow("surfaces must not be empty");
  });
});

// ---------------------------------------------------------------------------
// DescriptorRegistry
// ---------------------------------------------------------------------------

describe("createDescriptorRegistry", () => {
  function makeWidget(key: string) {
    return defineDashboardWidget({
      key,
      component: StubComponent,
      contract: {
        displayName: key,
        description: "",
        acceptsProps: [],
        capabilities: { reads: [], emits: [] },
        selfTests: [],
      },
    });
  }

  it("registers and retrieves sidebar widgets", () => {
    const registry = createDescriptorRegistry();
    registry.registerWidget(makeWidget("widget-a"));
    expect(registry.getWidget("widget-a")?.key).toBe("widget-a");
    expect(registry.getWidgetComponent("widget-a")).toBe(StubComponent);
    expect(registry.getWidgetComponent("missing")).toBeUndefined();
  });

  it("warns and overwrites duplicate sidebar widget", () => {
    const registry = createDescriptorRegistry();
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    registry.registerWidget(makeWidget("dup"));
    registry.registerWidget(makeWidget("dup"));
    expect(warnSpy).toHaveBeenCalledOnce();
    warnSpy.mockRestore();
  });

  it("filters importers by surface", () => {
    const registry = createDescriptorRegistry();
    registry.registerImporter(
      defineImporter({
        id: "dataset-only",
        label: "D",
        surfaces: ["dataset"],
        component: StubComponent,
      }),
    );
    registry.registerImporter(
      defineImporter({
        id: "both",
        label: "B",
        surfaces: ["dataset", "preview"],
        component: StubComponent,
      }),
    );
    expect(registry.getImporters("dataset").map((d) => d.id)).toEqual([
      "dataset-only",
      "both",
    ]);
    expect(registry.getImporters("preview").map((d) => d.id)).toEqual(["both"]);
  });

  it("filters agent skills by surface", () => {
    const registry = createDescriptorRegistry();
    registry.registerAgentSkill(
      defineAgentSkill({
        toolName: "classify_tool",
        displayName: "CT",
        description: "",
        surfaces: ["classify"],
      }),
    );
    registry.registerAgentSkill(
      defineAgentSkill({
        toolName: "global_tool",
        displayName: "GT",
        description: "",
        surfaces: ["global"],
      }),
    );
    expect(registry.getAgentSkills("classify").map((d) => d.toolName)).toEqual([
      "classify_tool",
    ]);
    expect(registry.getAgentSkillByToolName("global_tool")?.toolName).toBe(
      "global_tool",
    );
  });

  it("registers and filters preview launchers by surface", () => {
    const registry = createDescriptorRegistry();
    registry.registerPreviewLauncher(
      definePreviewLauncher({
        id: "upstream-preview",
        label: "Upstream",
        surfaces: ["dataset-list", "preview"],
        component: StubComponent,
      }),
    );
    registry.registerPreviewLauncher(
      definePreviewLauncher({
        id: "local-preview",
        label: "Local",
        surfaces: ["preview"],
        component: StubComponent,
      }),
    );
    expect(registry.getPreviewLaunchers("dataset-list").map((d) => d.id)).toEqual([
      "upstream-preview",
    ]);
    expect(registry.getPreviewLaunchers("preview").map((d) => d.id)).toEqual([
      "upstream-preview",
      "local-preview",
    ]);
  });

  it("warns and overwrites duplicate preview launcher", () => {
    const registry = createDescriptorRegistry();
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    registry.registerPreviewLauncher(
      definePreviewLauncher({
        id: "dup",
        label: "D1",
        surfaces: ["preview"],
        component: StubComponent,
      }),
    );
    registry.registerPreviewLauncher(
      definePreviewLauncher({
        id: "dup",
        label: "D2",
        surfaces: ["preview"],
        component: StubComponent,
      }),
    );
    expect(warnSpy).toHaveBeenCalledOnce();
    expect(registry.getPreviewLaunchers("preview")[0].label).toBe("D2");
    warnSpy.mockRestore();
  });
});

// ---------------------------------------------------------------------------
// reduceLabelFilterIntent
// ---------------------------------------------------------------------------

describe("reduceLabelFilterIntent", () => {
  const baseIntent: SidebarWidgetIntent = {
    type: "select-labels",
    operation: "replace",
    values: ["cat"],
  };

  it("replaces label on replace operation", () => {
    expect(reduceLabelFilterIntent(null, baseIntent)).toBe("cat");
    expect(reduceLabelFilterIntent("dog", baseIntent)).toBe("cat");
  });

  it("toggles off when same label clicked", () => {
    const intent: SidebarWidgetIntent = { ...baseIntent, operation: "toggle" };
    expect(reduceLabelFilterIntent("cat", intent)).toBeNull();
    expect(reduceLabelFilterIntent("dog", intent)).toBe("cat");
  });

  it("clears on clear-selection", () => {
    const intent: SidebarWidgetIntent = {
      ...baseIntent,
      type: "clear-selection",
      operation: "clear",
    };
    expect(reduceLabelFilterIntent("cat", intent)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// reduceCollectionIntent
// ---------------------------------------------------------------------------

describe("reduceCollectionIntent", () => {
  it("creates collection state on first intent", () => {
    const result = reduceCollectionIntent(undefined, {
      type: "select-samples",
      operation: "replace",
      values: ["s1", "s2"],
      metadata: {
        collection: "browser-items",
        entity: "sample",
        target: "selection",
      },
    });
    expect(result["browser-items"].selection.ids).toEqual(["s1", "s2"]);
    expect(result["browser-items"].filter.mode).toBe("all");
  });

  it("applies filter when target=filter", () => {
    const result = reduceCollectionIntent(undefined, {
      type: "apply-filter",
      operation: "replace",
      values: ["s1"],
      metadata: {
        collection: "browser-items",
        entity: "sample",
        target: "filter",
        filterMode: "selected-only",
      },
    });
    expect(result["browser-items"].filter.mode).toBe("selected-only");
    expect(result["browser-items"].filter.ids).toEqual(["s1"]);
  });

  it("clears collection on clear-selection", () => {
    const existing = {
      "browser-items": {
        entity: "sample" as const,
        selection: { ids: ["s1"], sourcePanelId: null, revision: 1 },
        filter: {
          ids: ["s1"],
          mode: "selected-only" as const,
          sourcePanelId: null,
          revision: 1,
        },
      },
    };
    const result = reduceCollectionIntent(existing, {
      type: "clear-selection",
      operation: "clear",
      values: [],
      metadata: { collection: "browser-items" },
    });
    expect(result["browser-items"].selection.ids).toEqual([]);
    expect(result["browser-items"].filter.mode).toBe("all");
  });

  it("no-ops when collection key is missing from metadata", () => {
    const result = reduceCollectionIntent(
      {
        existing: {
          entity: "sample",
          selection: { ids: ["x"], sourcePanelId: null, revision: 0 },
          filter: { ids: [], mode: "all", sourcePanelId: null, revision: 0 },
        },
      },
      { type: "select-samples", operation: "replace", values: ["y"] },
    );
    expect(result["existing"].selection.ids).toEqual(["x"]);
  });
});

// ---------------------------------------------------------------------------
// Regression: source barrel exports all expected names
// ---------------------------------------------------------------------------

describe("source barrel export completeness", () => {
  const EXPECTED_EXPORTS = [
    "BROWSER_DASHBOARD_KEY",
    "SIDEBAR_WIDGET_INTERACTION_KEY",
    "defineDashboardWidget",
    "reduceLabelFilterIntent",
    "reduceCollectionIntent",
    "defineImporter",
    "defineExporter",
    "defineAgentSkill",
    "definePreviewLauncher",
    "createDescriptorRegistry",
  ] as const;

  it("exports every expected named export from the source barrel", () => {
    for (const name of EXPECTED_EXPORTS) {
      expect(
        name in widgetSdk,
        `Expected "${name}" to be exported from index.ts`,
      ).toBe(true);
      expect(typeof (widgetSdk as Record<string, unknown>)[name]).not.toBe(
        "undefined",
      );
    }
  });
});

// ---------------------------------------------------------------------------
// Regression: built ESM dist contains all named exports
// ---------------------------------------------------------------------------

describe("built ESM dist export completeness", () => {
  const REQUIRED_EXPORTS = [
    "defineDashboardWidget",
    "defineImporter",
    "defineExporter",
    "defineAgentSkill",
    "definePreviewLauncher",
    "createDescriptorRegistry",
  ] as const;

  it("includes all named exports in the ESM dist output", () => {
    const distPath = resolve(__dirname, "../dist/index.js");
    let source: string;
    try {
      source = readFileSync(distPath, "utf-8");
    } catch {
      return;
    }
    const exportStart = source.indexOf("export {");
    expect(exportStart).toBeGreaterThan(-1);
    const exportBlock = source.slice(exportStart, source.indexOf("};", exportStart) + 2);
    for (const name of REQUIRED_EXPORTS) {
      expect(
        exportBlock.includes(name),
        `Expected "${name}" in ESM export clause`,
      ).toBe(true);
    }
  });
});
