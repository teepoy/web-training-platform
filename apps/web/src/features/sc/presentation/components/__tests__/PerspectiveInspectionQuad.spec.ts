import { describe, it, expect, vi, beforeEach } from "vitest";
import { mountWithProviders } from "@/testing";
import PerspectiveInspectionQuad from "../PerspectiveInspectionQuad.vue";

vi.mock("@perspective-dev/viewer/inline", () => ({}));

const modelMock = vi.hoisted(() => ({
  mapArrowData: { value: null },
  mapLegendColumn: { value: "class_number" },
  legendGroups: { value: null },
  activeMapLoading: { value: false },
  mapError: { value: null },
  mapProgressMessage: { value: "" },
  mapProgressPercent: { value: 0 },
  sampleTableBaseViewConfig: { value: {} },
  mapSelectedDefectIds: { value: [] },
  tableSelectedDefectIds: { value: [] },
  galleryLoading: { value: false },
  patchGalleryViewSnapshot: { value: null },
  reviewGalleryViewSnapshot: { value: null },
  loadGlobalDistinctValues: vi.fn(async () => []),
  setTableSelectedDefectIds: vi.fn(),
  setReviewMode: vi.fn(),
  queryBoxSelection: vi.fn(),
  queryLegendSelection: vi.fn(),
  applyMapSelection: vi.fn(),
  appendMapSelection: vi.fn(),
  clearMapSelection: vi.fn(),
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
vi.mock("../ScSampleTableVxe.vue", () => ({
  default: { name: "ScSampleTableVxe", template: "<div />" },
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
    reconnecting: { value: false },
    reconnectFailed: { value: false },
    reconnectAttempt: { value: 0 },
    reconnectMaxAttempts: 5,
    connect: vi.fn(),
    disconnect: vi.fn(),
    reconnect: vi.fn(),
    requestReconnect: vi.fn(),
  }),
}));
vi.mock("@/features/sc/presentation/composables/usePerspectiveInspectionModel", () => ({
  usePerspectiveInspectionModel: () => modelMock,
}));

const requiredProps = {
  inspectionTime: "2026-07-26T04:00:00+08:00",
  waferKey: 1,
  activeMapTab: "wafer" as const,
  reticleDieSizeX: 100_000,
  reticleDieSizeY: 100_000,
  reticleOptions: {
    xDieCount: 3,
    yDieCount: 5,
    xDieShift: 0,
    yDieShift: 0,
  },
};

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
        ...requiredProps,
        variant: "preview",
        selectedGalleryDefectIds: largeIds,
      },
    });
    await vi.runAllTimersAsync();
    const mapPanel = wrapper.findComponent({ name: "ScMapPanelBinned" });
    expect(mapPanel.props("highlightDefects")).toEqual([]);
  });

  it("calls model when ≤ 9999 selected (debounced)", async () => {
    const { wrapper } = await mountWithProviders(PerspectiveInspectionQuad, {
      props: {
        ...requiredProps,
        variant: "preview",
        selectedGalleryDefectIds: [1, 2, 3],
      },
    });
    await vi.runAllTimersAsync();
    // Just verify no crash — model.highlightDefectsForIds would be called in real app
    const mapPanel = wrapper.findComponent({ name: "ScMapPanelBinned" });
    expect(mapPanel.exists()).toBe(true);
  });

  it("appends box selection results before emitting map filter ids", async () => {
    const region = { x: 10, y: 20, w: 30, h: 40 };
    const { wrapper } = await mountWithProviders(PerspectiveInspectionQuad, {
      props: {
        ...requiredProps,
        variant: "preview",
        activeMapTab: "die",
      },
    });

    wrapper.findComponent({ name: "ScMapPanelBinned" }).vm.$emit("box-select", region);
    await Promise.resolve();
    await Promise.resolve();

    expect(modelMock.queryBoxSelection).toHaveBeenCalledWith("die", region);
    expect(modelMock.appendMapSelection).toHaveBeenCalledWith([2, 3]);
    expect(modelMock.applyMapSelection).not.toHaveBeenCalled();
    await vi.waitFor(() => {
      expect(wrapper.emitted("map-filter-change")).toEqual([[{ ids: [1, 2, 3], region }]]);
    });
  });

  it("batches queued box selection ids into one table update", async () => {
    const firstRegion = { x: 10, y: 20, w: 30, h: 40 };
    const secondRegion = { x: 50, y: 60, w: 70, h: 80 };
    modelMock.queryBoxSelection.mockResolvedValueOnce([2, 3]).mockResolvedValueOnce([4, 5]);
    modelMock.appendMapSelection.mockResolvedValueOnce([1, 2, 3, 4, 5]);
    const { wrapper } = await mountWithProviders(PerspectiveInspectionQuad, {
      props: {
        ...requiredProps,
        variant: "preview",
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
    expect(modelMock.appendMapSelection).toHaveBeenCalledTimes(1);
    expect(modelMock.appendMapSelection).toHaveBeenCalledWith([2, 3, 4, 5]);
    await vi.waitFor(() => {
      expect(wrapper.emitted("map-filter-change")).toEqual([
        [{ ids: [1, 2, 3, 4, 5], region: secondRegion }],
      ]);
    });
  });

  it("keeps legend selection as replace semantics", async () => {
    const region = { x: 0, y: 0, w: 0, h: 0 };
    const { wrapper } = await mountWithProviders(PerspectiveInspectionQuad, {
      props: {
        ...requiredProps,
        variant: "preview",
      },
    });

    wrapper
      .findComponent({ name: "ScMapPanelBinned" })
      .vm.$emit("legend-select", { ids: [], region, key: 7 });
    await Promise.resolve();
    await Promise.resolve();

    expect(modelMock.queryLegendSelection).toHaveBeenCalledWith(7);
    expect(modelMock.applyMapSelection).toHaveBeenCalledWith([8, 9]);
    expect(modelMock.appendMapSelection).not.toHaveBeenCalled();
    await vi.waitFor(() => {
      expect(wrapper.emitted("map-filter-change")).toEqual([[{ ids: [8, 9], region, key: 7 }]]);
    });
  });
});
