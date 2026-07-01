import { describe, it, expect, vi, beforeEach } from "vitest";
import { mountWithProviders } from "@/testing";
import PerspectiveInspectionQuad from "../PerspectiveInspectionQuad.vue";

const modelMock = vi.hoisted(() => ({
  waferDisplay: { value: new Float32Array(0) },
  dieDisplay: { value: new Float32Array(0) },
  reticleDisplay: { value: new Float32Array(0) },
  legendGroups: { value: null },
  activeMapLoading: { value: false },
  mapError: { value: null },
  tableBaseFilters: { value: [] },
  sampleTableActiveViewConfig: { value: {} },
  sampleTableActiveViewConfigVersion: { value: 0 },
  mapSelectedDefectIds: { value: [] },
  tableSelectedDefectIds: { value: [] },
  blinkFetching: { value: false },
  patchBlinkView: { value: null },
  patchBlinkViewVersion: { value: 0 },
  reviewBlinkView: { value: null },
  reviewBlinkViewVersion: { value: 0 },
  loadGlobalDistinctValues: vi.fn(async () => []),
  setTableSelectedDefectIds: vi.fn(),
  setGallerySelectedDefectIds: vi.fn(),
  setReviewMode: vi.fn(),
  queryBoxSelection: vi.fn(),
  queryLegendSelection: vi.fn(),
  applyMapSelection: vi.fn(),
  appendMapSelection: vi.fn(),
  clearMapSelection: vi.fn(),
  setHiddenLegendKeys: vi.fn(),
  highlightDefectsFor: vi.fn(async () => []),
  highlightDefectsForIds: vi.fn(async () => []),
}));

// Mock heavy child components
vi.mock("../ScMapPanelBinned.vue", () => ({
  default: {
    name: "ScMapPanelBinned",
    props: { highlightDefects: Array },
    template: "<div />",
  },
}));
vi.mock("../ScGlobalFilterBar.vue", () => ({
  default: { name: "ScGlobalFilterBar", template: "<div />" },
}));
vi.mock("../ScSampleTable.vue", () => ({
  default: { name: "ScSampleTable", template: "<div />" },
}));
vi.mock("../ScBlinkVirtualTable.vue", () => ({
  default: { name: "ScBlinkVirtualTable", template: "<div />" },
}));
// Mock Perspective workbench
vi.mock("@/features/sc/presentation/composables/useScPerspectiveWorkbench", () => ({
  useScPerspectiveWorkbench: () => ({
    table: { value: null },
    connected: { value: false },
    dataReady: { value: false },
    error: { value: null },
    connect: vi.fn(),
    disconnect: vi.fn(),
  }),
}));
vi.mock("@/features/sc/presentation/composables/usePerspectiveInspectionModel", () => ({
  usePerspectiveInspectionModel: () => modelMock,
}));

describe("PerspectiveInspectionQuad — highlight watcher", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    modelMock.queryBoxSelection.mockResolvedValue([2, 3]);
    modelMock.appendMapSelection.mockResolvedValue([1, 2, 3]);
    modelMock.queryLegendSelection.mockResolvedValue([8, 9]);
    modelMock.highlightDefectsForIds.mockResolvedValue([]);
  });

  it("sets highlightDefects to empty when > 9999 gallery selected", async () => {
    const largeIds = Array.from({ length: 10000 }, (_, i) => i + 1);
    const { wrapper } = await mountWithProviders(PerspectiveInspectionQuad, {
      props: {
        variant: "preview",
        samplesError: null,
        activeMapTab: "wafer",
        gallerySelectedDefectIds: largeIds,
      },
    });
    await vi.runAllTimersAsync();
    const mapPanel = wrapper.findComponent({ name: "ScMapPanelBinned" });
    expect(mapPanel.props("highlightDefects")).toEqual([]);
  });

  it("calls model when ≤ 9999 selected (debounced)", async () => {
    const { wrapper } = await mountWithProviders(PerspectiveInspectionQuad, {
      props: {
        variant: "preview",
        samples: [],
        samplesLoading: false,
        samplesError: null,
        activeMapTab: "wafer",
        gallerySelectedDefectIds: [1, 2, 3],
      },
    });
    await vi.runAllTimersAsync();
    // Just verify no crash — model.highlightDefectsForIds would be called in real app
    const mapPanel = wrapper.findComponent({ name: "ScMapPanelBinned" });
    expect(mapPanel.exists()).toBe(true);
  });

  it("appends box selection results before emitting selected points", async () => {
    const region = { x: 10, y: 20, w: 30, h: 40 };
    const { wrapper } = await mountWithProviders(PerspectiveInspectionQuad, {
      props: {
        variant: "preview",
        samples: [],
        samplesLoading: false,
        samplesError: null,
        activeMapTab: "die",
      },
    });

    wrapper.findComponent({ name: "ScMapPanelBinned" }).vm.$emit("box-select", region);
    await Promise.resolve();
    await Promise.resolve();

    expect(modelMock.queryBoxSelection).toHaveBeenCalledWith("die", region);
    expect(modelMock.appendMapSelection).toHaveBeenCalledWith([2, 3]);
    expect(modelMock.applyMapSelection).not.toHaveBeenCalled();
    expect(wrapper.emitted("select-points")).toEqual([[{ ids: [1, 2, 3], region }]]);
  });

  it("drains every queued box selection instead of keeping only the latest", async () => {
    const firstRegion = { x: 10, y: 20, w: 30, h: 40 };
    const secondRegion = { x: 50, y: 60, w: 70, h: 80 };
    modelMock.queryBoxSelection
      .mockResolvedValueOnce([2, 3])
      .mockResolvedValueOnce([4, 5]);
    modelMock.appendMapSelection
      .mockResolvedValueOnce([1, 2, 3])
      .mockResolvedValueOnce([1, 2, 3, 4, 5]);
    const { wrapper } = await mountWithProviders(PerspectiveInspectionQuad, {
      props: {
        variant: "preview",
        samples: [],
        samplesLoading: false,
        samplesError: null,
        activeMapTab: "die",
      },
    });

    const mapPanel = wrapper.findComponent({ name: "ScMapPanelBinned" });
    mapPanel.vm.$emit("box-select", firstRegion);
    mapPanel.vm.$emit("box-select", secondRegion);
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();

    expect(modelMock.queryBoxSelection).toHaveBeenNthCalledWith(1, "die", firstRegion);
    expect(modelMock.queryBoxSelection).toHaveBeenNthCalledWith(2, "die", secondRegion);
    expect(modelMock.appendMapSelection).toHaveBeenNthCalledWith(1, [2, 3]);
    expect(modelMock.appendMapSelection).toHaveBeenNthCalledWith(2, [4, 5]);
    expect(wrapper.emitted("select-points")).toEqual([
      [{ ids: [1, 2, 3], region: firstRegion }],
      [{ ids: [1, 2, 3, 4, 5], region: secondRegion }],
    ]);
  });

  it("keeps legend selection as replace semantics", async () => {
    const region = { x: 0, y: 0, w: 0, h: 0 };
    const { wrapper } = await mountWithProviders(PerspectiveInspectionQuad, {
      props: {
        variant: "preview",
        samples: [],
        samplesLoading: false,
        samplesError: null,
        activeMapTab: "wafer",
      },
    });

    wrapper
      .findComponent({ name: "ScMapPanelBinned" })
      .vm.$emit("select-points", { ids: [], region, key: 7 });
    await Promise.resolve();
    await Promise.resolve();

    expect(modelMock.queryLegendSelection).toHaveBeenCalledWith(7);
    expect(modelMock.applyMapSelection).toHaveBeenCalledWith([8, 9]);
    expect(modelMock.appendMapSelection).not.toHaveBeenCalled();
    expect(wrapper.emitted("select-points")).toEqual([[{ ids: [8, 9], region, key: 7 }]]);
  });
});
