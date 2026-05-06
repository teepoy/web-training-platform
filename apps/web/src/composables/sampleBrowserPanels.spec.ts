import { describe, it, expect } from "vitest";
import { ref } from "vue";
import {
  datasetPanels,
  previewPanels,
} from "../components/classify/sidebarConfig";
import { useBrowserFilter } from "./useBrowserFilter";
import type { BrowserItem } from "../types";
import type { SidebarWidgetInteractionState } from "../components/classify/widgetContract";

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

function makeBrowserItem(id: string, currentLabel: string | null = null, draftLabel: string | null = null): BrowserItem {
  return {
    id,
    imageSrcs: [],
    metadata: {},
    currentLabel,
    draftLabel,
    predictionLabel: null,
    predictionConfidence: null,
    predictionId: null,
    activationLabel: null,
  };
}

function makeInteractionState(overrides: Partial<SidebarWidgetInteractionState> = {}): SidebarWidgetInteractionState {
  return {
    activeLabelFilter: null,
    selectedLabels: [],
    collections: undefined,
    ...overrides,
  };
}

describe("useBrowserFilter", () => {
  it("returns all items when no filter is active", () => {
    const items = ref([
      makeBrowserItem("a"),
      makeBrowserItem("b"),
      makeBrowserItem("c"),
    ]);
    const state = ref(makeInteractionState());
    const { filteredItems } = useBrowserFilter(items, state);
    expect(filteredItems.value).toHaveLength(3);
  });

  it("filters by activeLabelFilter using currentLabel", () => {
    const items = ref([
      makeBrowserItem("a", "cat"),
      makeBrowserItem("b", "dog"),
      makeBrowserItem("c", "cat"),
    ]);
    const state = ref(makeInteractionState({ activeLabelFilter: "cat" }));
    const { filteredItems } = useBrowserFilter(items, state);
    expect(filteredItems.value.map((i) => i.id)).toEqual(["a", "c"]);
  });

  it("filters by activeLabelFilter using draftLabel", () => {
    const items = ref([
      makeBrowserItem("a", null, "cat"),
      makeBrowserItem("b", "dog", null),
      makeBrowserItem("c", "cat", null),
    ]);
    const state = ref(makeInteractionState({ activeLabelFilter: "cat" }));
    const { filteredItems } = useBrowserFilter(items, state);
    expect(filteredItems.value.map((i) => i.id)).toEqual(["a", "c"]);
  });

  it("filters by browser-items collection filter IDs when mode is selected-only", () => {
    const items = ref([
      makeBrowserItem("a"),
      makeBrowserItem("b"),
      makeBrowserItem("c"),
    ]);
    const state = ref(
      makeInteractionState({
        collections: {
          "browser-items": {
            entity: "sample",
            selection: { ids: [], sourcePanelId: null, revision: 0 },
            filter: { ids: ["a", "c"], mode: "selected-only", sourcePanelId: null, revision: 1 },
          },
        },
      }),
    );
    const { filteredItems } = useBrowserFilter(items, state);
    expect(filteredItems.value.map((i) => i.id)).toEqual(["a", "c"]);
  });

  it("does not filter by browser-items collection when mode is all", () => {
    const items = ref([
      makeBrowserItem("a"),
      makeBrowserItem("b"),
    ]);
    const state = ref(
      makeInteractionState({
        collections: {
          "browser-items": {
            entity: "sample",
            selection: { ids: [], sourcePanelId: null, revision: 0 },
            filter: { ids: ["a"], mode: "all", sourcePanelId: null, revision: 1 },
          },
        },
      }),
    );
    const { filteredItems } = useBrowserFilter(items, state);
    expect(filteredItems.value).toHaveLength(2);
  });

  it("filters by custom collection key when provided", () => {
    const items = ref([
      makeBrowserItem("a"),
      makeBrowserItem("b"),
      makeBrowserItem("c"),
    ]);
    const state = ref(
      makeInteractionState({
        collections: {
          "classify-samples": {
            entity: "sample",
            selection: { ids: [], sourcePanelId: null, revision: 0 },
            filter: { ids: ["b", "c"], mode: "selected-only", sourcePanelId: null, revision: 1 },
          },
        },
      }),
    );
    const { filteredItems } = useBrowserFilter(items, state, "classify-samples");
    expect(filteredItems.value.map((i) => i.id)).toEqual(["b", "c"]);
  });
});
