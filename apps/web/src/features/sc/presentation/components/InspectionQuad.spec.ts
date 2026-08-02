import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ScSampleTableFilter } from "@/features/sc/domain/sampleTable";
import type { ScSampleTableDataSource } from "@/features/sc/domain/workbenchInteraction";
import { mountWithProviders } from "@/testing";
import InspectionQuad from "./InspectionQuad.vue";

const harness = vi.hoisted(() => ({
  options: null as {
    globalFilter: { value: ScSampleTableFilter };
    legendGroupBy: { value: string | null | undefined };
    tableFilter: { value: ScSampleTableFilter | undefined };
    tableSort: { value: unknown };
    reticle: { value: { options: unknown; dieSizeX: number; dieSizeY: number } };
  } | null,
}));

const model = vi.hoisted(() => ({
  mapArrowData: { value: null },
  mapLegendColumn: { value: "class_number" },
  legendGroups: { value: null },
  activeMapLoading: { value: false },
  mapError: { value: null },
  mapProgressMessage: { value: "" },
  mapProgressPercent: { value: 0 },
  retryMap: vi.fn(async () => undefined),
  sampleTableDataSource: { value: undefined as ScSampleTableDataSource | undefined },
  galleryLoading: { value: false },
  galleryQuery: { value: {} },
  mapSelectedDefectIds: { value: [] },
  reviewMode: { value: false },
  tableSelection: { value: { kind: "ids", ids: [] } },
  loadGlobalDistinctValues: vi.fn(async () => []),
  loadGlobalNumericRange: vi.fn(async () => null),
  setTableSelection: vi.fn(),
  setReviewMode: vi.fn(),
  queryBoxSelection: vi.fn(async () => []),
  queryLassoSelection: vi.fn(async () => []),
  queryLegendSelection: vi.fn(async () => []),
  querySamplingCandidateCount: vi.fn(async () => 0),
  querySamplingDefectIds: vi.fn(async () => []),
  applyMapSelection: vi.fn(async () => undefined),
  appendMapSelection: vi.fn(async () => []),
  clearMapSelection: vi.fn(async () => undefined),
}));

vi.mock("vue-echarts", () => ({
  default: { name: "VChart", template: "<div />" },
}));
vi.mock("./ScMapPanelBinned.vue", () => ({
  default: {
    name: "ScMapPanelBinned",
    props: [
      "activeMapTab",
      "zoom",
      "reticleOptions",
      "legendGroupBy",
      "waferGeometry",
      "highlightDefectIds",
      "immediateCrosshairDefectIds",
    ],
    emits: [
      "update:activeMapTab",
      "update:reticleOptions",
      "zoom-in",
      "legend-group-change",
      "legend-select",
      "retry",
    ],
    template: "<div />",
  },
}));
vi.mock("./ScGlobalFilterModal.vue", () => ({
  default: {
    name: "ScGlobalFilterModal",
    props: ["show", "filter", "distinctValues", "numericRanges", "numericRangeLoading"],
    emits: ["update:show", "update:filter", "search-options", "request-range"],
    template: "<div />",
  },
}));
vi.mock("./ScSampleTableVxe.vue", () => ({
  default: {
    name: "ScSampleTableVxe",
    props: ["filter", "sort", "selection"],
    emits: ["filter-change", "sort-change", "selection-change"],
    template: "<div />",
  },
}));
vi.mock("./ScBlinkVirtualTable.vue", () => ({
  default: {
    name: "ScBlinkVirtualTable",
    props: ["selectedDefectIds"],
    emits: ["select-samples", "mode-change"],
    template: "<div />",
  },
}));
vi.mock("@/features/sc/presentation/composables/useInspectionQuadData", () => ({
  useInspectionQuadData: (options: (typeof harness)["options"]) => {
    harness.options = options;
    return {
      workbench: {
        dataSource: { value: null },
      },
      dataReady: { value: true },
      model,
      reportDataError: vi.fn(),
    };
  },
}));

const requiredProps = {
  inspectionTime: "2026-07-26T04:00:00+08:00",
  waferKey: 1,
};

describe("InspectionQuad state ownership", () => {
  it("removes the toolbar grid row when the global filter trigger is teleported", async () => {
    const target = document.createElement("div");
    target.id = "global-filter-target";
    document.body.append(target);
    const { wrapper } = await mountWithProviders(InspectionQuad, {
      props: {
        variant: "reclassify",
        datasetId: "dataset-1",
        inspectionTime: "2026-08-01T04:00:00+08:00",
        waferKey: 1,
        globalFilterTriggerTarget: "#global-filter-target",
      },
      attachTo: document.body,
    });

    expect(wrapper.get(".iq-panel-left").attributes("style")).toContain(
      "grid-template-rows: 55fr 10px 45fr",
    );
    wrapper.unmount();
    target.remove();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    model.sampleTableDataSource.value = undefined;
    model.reviewMode.value = false;
    model.loadGlobalDistinctValues.mockReset().mockResolvedValue([]);
    model.loadGlobalNumericRange.mockReset().mockResolvedValue(null);
  });

  it("keeps the latest global-filter search result when requests finish out of order", async () => {
    let resolveInitial!: (values: Array<string | number>) => void;
    let resolveSearch!: (values: Array<string | number>) => void;
    model.loadGlobalDistinctValues
      .mockImplementationOnce(
        () => new Promise<Array<string | number>>((resolve) => (resolveInitial = resolve)),
      )
      .mockImplementationOnce(
        () => new Promise<Array<string | number>>((resolve) => (resolveSearch = resolve)),
      );
    const { wrapper } = await mountWithProviders(InspectionQuad, {
      props: requiredProps,
    });
    const filterModal = wrapper.findComponent({ name: "ScGlobalFilterModal" });

    filterModal.vm.$emit("search-options", { field: "test_id", search: "" });
    filterModal.vm.$emit("search-options", { field: "test_id", search: "936" });
    resolveSearch([936]);
    await vi.waitFor(() => {
      expect(filterModal.props("distinctValues")).toEqual({ test_id: [936] });
    });

    resolveInitial([1, 2, 3]);
    await wrapper.vm.$nextTick();
    expect(filterModal.props("distinctValues")).toEqual({ test_id: [936] });
  });

  it("loads numeric bounds when a global range filter opens", async () => {
    model.loadGlobalNumericRange.mockResolvedValue({ min: 1.25, max: 98.5 });
    const { wrapper } = await mountWithProviders(InspectionQuad, {
      props: requiredProps,
    });
    const filterModal = wrapper.findComponent({ name: "ScGlobalFilterModal" });

    filterModal.vm.$emit("request-range", "area");

    await vi.waitFor(() => {
      expect(filterModal.props("numericRanges")).toEqual({
        area: { min: 1.25, max: 98.5 },
      });
    });
    expect(model.loadGlobalNumericRange).toHaveBeenCalledWith("area");
    expect(filterModal.props("numericRangeLoading")).toEqual({ area: false });
  });

  it("owns filter updates and exposes only a cloned workflow snapshot", async () => {
    const { wrapper } = await mountWithProviders(InspectionQuad, {
      props: requiredProps,
    });
    const filter: ScSampleTableFilter = {
      rough_bin: { filterType: "set", values: [1, 2] },
    };

    const filterModal = wrapper.findComponent({ name: "ScGlobalFilterModal" });
    expect(filterModal.props("show")).toBe(false);
    await wrapper.get("button").trigger("click");
    expect(filterModal.props("show")).toBe(true);

    filterModal.vm.$emit("update:filter", filter);
    await wrapper.vm.$nextTick();

    expect(harness.options?.globalFilter.value).toEqual(filter);
    const exposed = wrapper.vm as unknown as {
      getGlobalFilter: () => ScSampleTableFilter;
    };
    const snapshot = exposed.getGlobalFilter();
    expect(snapshot).toEqual(filter);
    if (snapshot.rough_bin?.filterType === "set") snapshot.rough_bin.values.push(99);
    expect(exposed.getGlobalFilter()).toEqual(filter);
    expect(wrapper.emitted("update:global-filter")).toBeUndefined();
  });

  it("retries only the failed map query from the map error action", async () => {
    const { wrapper } = await mountWithProviders(InspectionQuad, {
      props: requiredProps,
    });

    wrapper.findComponent({ name: "ScMapPanelBinned" }).vm.$emit("retry");
    await wrapper.vm.$nextTick();

    expect(model.retryMap).toHaveBeenCalledOnce();
  });

  it("clears local filter state when the inspection scope changes", async () => {
    const { wrapper } = await mountWithProviders(InspectionQuad, {
      props: requiredProps,
    });
    wrapper.findComponent({ name: "ScGlobalFilterModal" }).vm.$emit("update:filter", {
      class_number: { filterType: "set", values: [7] },
    });
    await wrapper.vm.$nextTick();

    await wrapper.setProps({ inspectionTime: "2026-07-27T04:00:00+08:00" });

    expect(harness.options?.globalFilter.value).toEqual({});
  });

  it("keeps map, reticle, legend, table filter and sort state inside the quad", async () => {
    model.sampleTableDataSource.value = {
      scopeKey: "test-scope",
      loadRows: vi.fn(async () => ({ items: [], total: 0, nextAnchor: null })),
    };
    const { wrapper } = await mountWithProviders(InspectionQuad, {
      props: requiredProps,
    });
    const map = wrapper.findComponent({ name: "ScMapPanelBinned" });
    const table = wrapper.findComponent({ name: "ScSampleTableVxe" });
    const viewport = { x: 1, y: 2, w: 3, h: 4 };
    const nextReticle = { xDieCount: 4, yDieCount: 6, xDieShift: 1, yDieShift: -1 };
    const filter: ScSampleTableFilter = {
      rough_bin: { filterType: "set", values: [7] },
    };

    map.vm.$emit("update:activeMapTab", "die");
    map.vm.$emit("zoom-in", viewport);
    map.vm.$emit("update:reticleOptions", nextReticle);
    map.vm.$emit("legend-group-change", "bin");
    table.vm.$emit("filter-change", filter);
    table.vm.$emit("sort-change", { field: "defect_id", direction: "desc" });
    await wrapper.vm.$nextTick();

    expect(map.props("activeMapTab")).toBe("die");
    expect(map.props("zoom")).toEqual(viewport);
    expect(harness.options?.reticle.value.options).toEqual(nextReticle);
    expect(harness.options?.legendGroupBy.value).toBe("bin");
    expect(harness.options?.tableFilter.value).toEqual(filter);
    expect(harness.options?.tableSort.value).toEqual({
      field: "defect_id",
      direction: "desc",
    });
    expect(wrapper.emitted("update:activeMapTab")).toBeUndefined();
    expect(wrapper.emitted("update:tableFilter")).toBeUndefined();
  });

  it("keeps table select-all as a local gallery constraint", async () => {
    model.sampleTableDataSource.value = {
      scopeKey: "test-scope",
      loadRows: vi.fn(async () => ({ items: [], total: 300_000, nextAnchor: null })),
    };
    const { wrapper } = await mountWithProviders(InspectionQuad, {
      props: { ...requiredProps, variant: "reclassify", selectedDefectIds: [] },
    });

    wrapper.findComponent({ name: "ScSampleTableVxe" }).vm.$emit("selection-change", {
      kind: "all",
      excludedIds: [],
    });

    expect(model.setTableSelection).toHaveBeenCalledWith({ kind: "all", excludedIds: [] });
    expect(wrapper.emitted("selection-change")).toBeUndefined();
  });

  it("owns Preview selection without involving a parent", async () => {
    const { wrapper } = await mountWithProviders(InspectionQuad, {
      props: requiredProps,
    });
    const gallery = wrapper.findComponent({ name: "ScBlinkVirtualTable" });

    gallery.vm.$emit("select-samples", ["103", "274"], {
      shift: true,
      ctrl: false,
      meta: false,
      selectionMode: "replace",
    });
    await wrapper.vm.$nextTick();

    expect([...gallery.props("selectedDefectIds")]).toEqual(["103", "274"]);
    expect(wrapper.findComponent({ name: "ScMapPanelBinned" }).props("highlightDefectIds")).toEqual(
      [103, 274],
    );
    expect(wrapper.emitted("selection-change")).toBeUndefined();
  });

  it("emits one normalized action for controlled Reclassify selection", async () => {
    const { wrapper } = await mountWithProviders(InspectionQuad, {
      props: { ...requiredProps, variant: "reclassify", selectedDefectIds: [] },
    });

    wrapper.findComponent({ name: "ScBlinkVirtualTable" }).vm.$emit("select-samples", ["103"], {
      shift: false,
      ctrl: true,
      meta: false,
      selectionMode: "toggle",
    });

    expect(wrapper.emitted("selection-change")?.[0]).toEqual([
      { source: "blink-table", ids: ["103"], mode: "toggle" },
    ]);
  });

  it("keeps map selection local while invalidating active random sampling", async () => {
    const { wrapper } = await mountWithProviders(InspectionQuad, {
      props: {
        ...requiredProps,
        galleryRandomSamplingDefectIds: new Set(["103", "274"]),
      },
    });

    wrapper.findComponent({ name: "ScMapPanelBinned" }).vm.$emit("legend-select", 7);

    await vi.waitFor(() => {
      expect(model.applyMapSelection).toHaveBeenCalledWith([]);
    });
    expect(wrapper.emitted("clear-gallery-random-sampling")).toHaveLength(1);
  });

  it("clears an active sampling cohort when Review mode changes", async () => {
    const { wrapper } = await mountWithProviders(InspectionQuad, {
      props: {
        ...requiredProps,
        galleryRandomSamplingDefectIds: new Set(["103"]),
      },
    });

    wrapper.findComponent({ name: "ScBlinkVirtualTable" }).vm.$emit("mode-change", "review");

    expect(model.setReviewMode).toHaveBeenCalledWith(true);
    expect(wrapper.emitted("clear-gallery-random-sampling")).toHaveLength(1);
  });
});
