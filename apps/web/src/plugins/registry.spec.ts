import { describe, expect, it } from "vitest";

import { defaultPanels, datasetPanels, previewPanels } from "../components/classify/sidebarConfig";
import { pluginRegistry } from "../core/registry";
import "./index";

describe("plugin registration", () => {
  it("registers every sidebar plugin used by panel presets", () => {
    const panels = [...defaultPanels, ...datasetPanels, ...previewPanels];

    for (const panel of panels) {
      expect(
        pluginRegistry.getSidebarWidget(panel.component),
        `missing sidebar plugin: ${panel.component}`,
      ).toBeDefined();
    }
  });

  it("registers dataset importers, exporters, and preview launchers explicitly", () => {
    expect(pluginRegistry.getImporters("dataset").map((plugin) => plugin.id)).toEqual([
      "import-manual",
      "import-dataset-manual",
      "import-parquet",
    ]);
    expect(pluginRegistry.getExporters("dataset").map((plugin) => plugin.id)).toEqual([
      "export-preview",
      "export-persist",
      "export-parquet",
    ]);
    expect(pluginRegistry.getPreviewLaunchers("dataset-list").map((plugin) => plugin.id)).toEqual([
      "preview-upstream",
    ]);
  });
});
