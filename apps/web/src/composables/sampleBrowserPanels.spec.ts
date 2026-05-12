import { describe, it, expect } from "vitest";
import {
  datasetPanels,
  previewPanels,
} from "../components/classify/sidebarConfig";

const CLASSIFY_ONLY = ["annotation-progress", "sample-viewer", "selected-samples"];
const REQUIRED_IN_DATASET_BROWSER = ["label-distribution", "wafer-map", "browser-summary"];
const REQUIRED_IN_PREVIEW_BROWSER = ["label-distribution", "wafer-map", "browser-summary"];

describe("datasetPanels preset", () => {
  it("does not include classify-only widgets", () => {
    const ids = datasetPanels.map((p) => p.id);
    for (const excluded of CLASSIFY_ONLY) {
      expect(ids).not.toContain(excluded);
    }
  });

  it("includes required browser widgets", () => {
    const ids = datasetPanels.map((p) => p.id);
    for (const required of REQUIRED_IN_DATASET_BROWSER) {
      expect(ids).toContain(required);
    }
  });

  it("enables wafer-map linked filtering for browser-items", () => {
    const waferMapPanel = datasetPanels.find((panel) => panel.id === "wafer-map");
    expect(waferMapPanel).toBeDefined();
    expect(waferMapPanel?.props.config).toMatchObject({
      interaction: {
        collection: "browser-items",
        entity: "sample",
        emitSelection: true,
        followSelection: true,
        filterFromSelection: true,
      },
    });
  });
});

describe("previewPanels preset", () => {
  it("does not include classify-only widgets", () => {
    const ids = previewPanels.map((p) => p.id);
    for (const excluded of CLASSIFY_ONLY) {
      expect(ids).not.toContain(excluded);
    }
  });

  it("includes required browser widgets", () => {
    const ids = previewPanels.map((p) => p.id);
    for (const required of REQUIRED_IN_PREVIEW_BROWSER) {
      expect(ids).toContain(required);
    }
  });
});
