import { describe, expect, it } from "vitest";

import { defaultPanels, datasetPanels, previewPanels } from "../components/classify/sidebarConfig";
import { widgetRegistry } from "../core/registry";
import "./index";

describe("widget registration", () => {
  it("registers every sidebar plugin used by panel presets", () => {
    const panels = [...defaultPanels, ...datasetPanels, ...previewPanels];

    for (const panel of panels) {
      expect(
        widgetRegistry.getWidget(panel.component),
        `missing sidebar widget: ${panel.component}`,
      ).toBeDefined();
    }
  });

  it("registers dataset importers, exporters, and preview launchers explicitly", () => {
    expect(widgetRegistry.getImporters("dataset").map((d) => d.id)).toEqual([
      "import-manual",
      "import-dataset-manual",
      "import-parquet",
    ]);
    expect(widgetRegistry.getExporters("dataset").map((d) => d.id)).toEqual([
      "export-preview",
      "export-persist",
      "export-parquet",
    ]);
    expect(widgetRegistry.getPreviewLaunchers("dataset-list").map((d) => d.id)).toEqual([
      "preview-upstream",
    ]);
  });
});
