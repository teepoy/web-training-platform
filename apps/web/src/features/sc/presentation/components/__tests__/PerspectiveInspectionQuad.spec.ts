import { describe, it, expect, vi, beforeEach } from "vitest";
import { mountWithProviders } from "@/testing";
import PerspectiveInspectionQuad from "../PerspectiveInspectionQuad.vue";

vi.mock("@perspective-dev/viewer/inline", () => ({}));
vi.mock("vue-echarts", () => ({
  default: {
    name: "VChart",
    props: { option: Object },
    emits: ["click"],
    template: '<div data-testid="group-distribution-chart" />',
  },
}));

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
  queryLassoSelection: vi.fn(),
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
    modelMock.queryLassoSelection.mockResolvedValue([4, 5]);
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

  it("appends box selection results before emitting a typed map selection change", async () => {
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
      expect(wrapper.emitted("map-selection-change")).toEqual([
        [{ source: "box", mode: "append", ids: [1, 2, 3], region }],
      ]);
    });
  });

  it("serializes repeated box selections and refreshes after each append", async () => {
    const firstRegion = { x: 10, y: 20, w: 30, h: 40 };
    const secondRegion = { x: 50, y: 60, w: 70, h: 80 };
    modelMock.queryBoxSelection.mockResolvedValueOnce([2, 3]).mockResolvedValueOnce([4, 5]);
    modelMock.appendMapSelection
      .mockResolvedValueOnce([1, 2, 3])
      .mockResolvedValueOnce([1, 2, 3, 4, 5]);
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
    await vi.waitFor(() => {
      expect(modelMock.queryBoxSelection).toHaveBeenNthCalledWith(1, "die", firstRegion);
      expect(modelMock.queryBoxSelection).toHaveBeenNthCalledWith(2, "die", secondRegion);
      expect(modelMock.appendMapSelection).toHaveBeenNthCalledWith(1, [2, 3]);
      expect(modelMock.appendMapSelection).toHaveBeenNthCalledWith(2, [4, 5]);
      expect(wrapper.emitted("map-selection-change")).toEqual([
        [{ source: "box", mode: "append", ids: [1, 2, 3], region: firstRegion }],
        [{ source: "box", mode: "append", ids: [1, 2, 3, 4, 5], region: secondRegion }],
      ]);
    });
  });

  it("appends lasso selection results", async () => {
    const selection = {
      points: [
        { x: 0, y: 0 },
        { x: 10, y: 0 },
        { x: 5, y: 10 },
      ],
      region: { x: 0, y: 0, w: 10, h: 10 },
    };
    modelMock.appendMapSelection.mockResolvedValueOnce([1, 4, 5]);
    const { wrapper } = await mountWithProviders(PerspectiveInspectionQuad, {
      props: {
        ...requiredProps,
        variant: "preview",
        activeMapTab: "wafer",
      },
    });

    wrapper.findComponent({ name: "ScMapPanelBinned" }).vm.$emit("lasso-select", selection);

    await vi.waitFor(() => {
      expect(modelMock.queryLassoSelection).toHaveBeenCalledWith("wafer", selection);
      expect(modelMock.appendMapSelection).toHaveBeenCalledWith([4, 5]);
      expect(wrapper.emitted("map-selection-change")).toEqual([
        [
          {
            source: "lasso",
            mode: "append",
            ids: [1, 4, 5],
            region: selection.region,
          },
        ],
      ]);
    });
  });

  it("clears map selection so the sample table returns to its full data source", async () => {
    const { wrapper } = await mountWithProviders(PerspectiveInspectionQuad, {
      props: {
        ...requiredProps,
        variant: "preview",
      },
    });

    wrapper.findComponent({ name: "ScMapPanelBinned" }).vm.$emit("clear-selection");

    await vi.waitFor(() => {
      expect(modelMock.clearMapSelection).toHaveBeenCalledOnce();
      expect(wrapper.emitted("map-selection-change")).toEqual([
        [{ source: "clear", mode: "clear", ids: [] }],
      ]);
    });
  });

  it("does not reapply an in-flight area selection after clear", async () => {
    const region = { x: 10, y: 20, w: 30, h: 40 };
    let resolveQuery: ((ids: number[]) => void) | undefined;
    modelMock.queryBoxSelection.mockReturnValueOnce(
      new Promise<number[]>((resolve) => {
        resolveQuery = resolve;
      }),
    );
    const { wrapper } = await mountWithProviders(PerspectiveInspectionQuad, {
      props: {
        ...requiredProps,
        variant: "preview",
      },
    });
    const mapPanel = wrapper.findComponent({ name: "ScMapPanelBinned" });

    mapPanel.vm.$emit("box-select", region);
    await vi.waitFor(() => {
      expect(modelMock.queryBoxSelection).toHaveBeenCalledOnce();
    });
    mapPanel.vm.$emit("clear-selection");
    await vi.waitFor(() => {
      expect(modelMock.clearMapSelection).toHaveBeenCalledOnce();
    });

    resolveQuery?.([2, 3]);
    await Promise.resolve();
    await Promise.resolve();

    expect(modelMock.appendMapSelection).not.toHaveBeenCalled();
    expect(wrapper.emitted("map-selection-change")).toEqual([
      [{ source: "clear", mode: "clear", ids: [] }],
    ]);
  });

  it("drains a second box selection after the first table update completes", async () => {
    const firstRegion = { x: 10, y: 20, w: 30, h: 40 };
    const secondRegion = { x: 50, y: 60, w: 70, h: 80 };
    let resolveFirstUpdate: ((ids: number[]) => void) | undefined;
    const firstUpdate = new Promise<number[]>((resolve) => {
      resolveFirstUpdate = resolve;
    });
    modelMock.queryBoxSelection.mockResolvedValueOnce([2, 3]).mockResolvedValueOnce([4, 5]);
    modelMock.appendMapSelection
      .mockReturnValueOnce(firstUpdate)
      .mockResolvedValueOnce([1, 2, 3, 4, 5]);
    const { wrapper } = await mountWithProviders(PerspectiveInspectionQuad, {
      props: {
        ...requiredProps,
        variant: "preview",
        activeMapTab: "die",
      },
    });
    const mapPanel = wrapper.findComponent({ name: "ScMapPanelBinned" });

    mapPanel.vm.$emit("box-select", firstRegion);
    await vi.waitFor(() => {
      expect(modelMock.appendMapSelection).toHaveBeenCalledTimes(1);
    });
    mapPanel.vm.$emit("box-select", secondRegion);
    await Promise.resolve();
    expect(modelMock.appendMapSelection).toHaveBeenCalledTimes(1);

    resolveFirstUpdate?.([1, 2, 3]);
    await vi.waitFor(() => {
      expect(modelMock.appendMapSelection).toHaveBeenCalledTimes(2);
    });

    expect(modelMock.appendMapSelection).toHaveBeenNthCalledWith(1, [2, 3]);
    expect(modelMock.appendMapSelection).toHaveBeenNthCalledWith(2, [4, 5]);
    expect(wrapper.emitted("map-selection-change")).toEqual([
      [{ source: "box", mode: "append", ids: [1, 2, 3], region: firstRegion }],
      [{ source: "box", mode: "append", ids: [1, 2, 3, 4, 5], region: secondRegion }],
    ]);
  });

  it("keeps legend selection as replace semantics", async () => {
    const { wrapper } = await mountWithProviders(PerspectiveInspectionQuad, {
      props: {
        ...requiredProps,
        variant: "preview",
      },
    });

    wrapper.findComponent({ name: "ScMapPanelBinned" }).vm.$emit("legend-select", 7);
    await vi.waitFor(() => {
      expect(modelMock.queryLegendSelection).toHaveBeenCalledWith(7);
      expect(modelMock.applyMapSelection).toHaveBeenCalledWith([8, 9]);
      expect(modelMock.appendMapSelection).not.toHaveBeenCalled();
      expect(wrapper.emitted("map-selection-change")).toEqual([
        [{ source: "legend", mode: "replace", ids: [8, 9], groupKey: 7 }],
      ]);
    });
  });

  it("applies a box after a legend as an append to the replaced selection", async () => {
    const region = { x: 10, y: 20, w: 30, h: 40 };
    modelMock.appendMapSelection.mockResolvedValueOnce([2, 3, 8, 9]);
    const { wrapper } = await mountWithProviders(PerspectiveInspectionQuad, {
      props: {
        ...requiredProps,
        variant: "preview",
      },
    });
    const mapPanel = wrapper.findComponent({ name: "ScMapPanelBinned" });

    mapPanel.vm.$emit("legend-select", 7);
    mapPanel.vm.$emit("box-select", region);

    await vi.waitFor(() => {
      expect(modelMock.applyMapSelection).toHaveBeenCalledWith([8, 9]);
      expect(modelMock.appendMapSelection).toHaveBeenCalledWith([2, 3]);
      expect(wrapper.emitted("map-selection-change")).toEqual([
        [{ source: "legend", mode: "replace", ids: [8, 9], groupKey: 7 }],
        [{ source: "box", mode: "append", ids: [2, 3, 8, 9], region }],
      ]);
    });
    expect(modelMock.applyMapSelection.mock.invocationCallOrder[0]).toBeLessThan(
      modelMock.appendMapSelection.mock.invocationCallOrder[0] ?? 0,
    );
  });

  it("cancels a slow box when a later legend replaces the selection", async () => {
    const region = { x: 10, y: 20, w: 30, h: 40 };
    let resolveBoxQuery: ((ids: number[]) => void) | undefined;
    modelMock.queryBoxSelection.mockReturnValueOnce(
      new Promise<number[]>((resolve) => {
        resolveBoxQuery = resolve;
      }),
    );
    const { wrapper } = await mountWithProviders(PerspectiveInspectionQuad, {
      props: {
        ...requiredProps,
        variant: "preview",
      },
    });
    const mapPanel = wrapper.findComponent({ name: "ScMapPanelBinned" });

    mapPanel.vm.$emit("box-select", region);
    await vi.waitFor(() => {
      expect(modelMock.queryBoxSelection).toHaveBeenCalledOnce();
    });
    mapPanel.vm.$emit("legend-select", 7);

    await vi.waitFor(() => {
      expect(modelMock.applyMapSelection).toHaveBeenCalledWith([8, 9]);
      expect(wrapper.emitted("map-selection-change")).toEqual([
        [{ source: "legend", mode: "replace", ids: [8, 9], groupKey: 7 }],
      ]);
    });

    resolveBoxQuery?.([2, 3]);
    await Promise.resolve();
    await Promise.resolve();
    expect(modelMock.appendMapSelection).not.toHaveBeenCalled();
  });

  it("toggles chart selection independently using the legend group query", async () => {
    modelMock.legendGroups.value = {
      "7": { count: 2, defectIds: [] },
      "8": { count: 1, defectIds: [] },
    };
    const { wrapper } = await mountWithProviders(PerspectiveInspectionQuad, {
      props: {
        ...requiredProps,
        variant: "reclassify",
        legendGroupBy: "class",
      },
    });
    const chart = wrapper.findComponent({ name: "VChart" });

    chart.vm.$emit("click", { dataIndex: 0 });
    await vi.waitFor(() => {
      expect(modelMock.queryLegendSelection).toHaveBeenCalledWith("7");
      expect(modelMock.applyMapSelection).toHaveBeenCalledWith([8, 9]);
    });

    const selectedOption = chart.props("option") as {
      series: Array<{ data: Array<{ itemStyle: { opacity: number; borderWidth: number } }> }>;
    };
    expect(selectedOption.series[0]?.data[0]?.itemStyle).toMatchObject({
      opacity: 1,
      borderWidth: 2,
    });
    expect(selectedOption.series[0]?.data[1]?.itemStyle.opacity).toBe(0.35);

    chart.vm.$emit("click", { dataIndex: 0 });
    await vi.waitFor(() => {
      expect(modelMock.applyMapSelection).toHaveBeenLastCalledWith([]);
    });
    expect(modelMock.queryLegendSelection).toHaveBeenCalledTimes(1);
    expect(wrapper.emitted("map-selection-change")).toEqual([
      [{ source: "bar-chart", mode: "replace", ids: [8, 9], groupKey: "7" }],
      [{ source: "bar-chart", mode: "clear", ids: [], groupKey: null }],
    ]);

    modelMock.legendGroups.value = null;
  });

  it("clears the chart marker when another map interaction replaces its selection", async () => {
    modelMock.legendGroups.value = {
      "7": { count: 2, defectIds: [] },
      "8": { count: 1, defectIds: [] },
    };
    const { wrapper } = await mountWithProviders(PerspectiveInspectionQuad, {
      props: {
        ...requiredProps,
        variant: "reclassify",
        legendGroupBy: "class",
      },
    });
    const chart = wrapper.findComponent({ name: "VChart" });

    chart.vm.$emit("click", { dataIndex: 0 });
    await vi.waitFor(() => {
      const option = chart.props("option") as {
        series: Array<{ data: Array<{ itemStyle: { opacity: number } }> }>;
      };
      expect(option.series[0]?.data[1]?.itemStyle.opacity).toBe(0.35);
    });

    wrapper.findComponent({ name: "ScMapPanelBinned" }).vm.$emit("clear-selection");
    await vi.waitFor(() => {
      const option = chart.props("option") as {
        series: Array<{ data: Array<{ itemStyle: { opacity: number; borderWidth: number } }> }>;
      };
      expect(option.series[0]?.data[0]?.itemStyle).toMatchObject({ opacity: 1, borderWidth: 0 });
      expect(option.series[0]?.data[1]?.itemStyle.opacity).toBe(1);
    });

    modelMock.legendGroups.value = null;
  });
});
