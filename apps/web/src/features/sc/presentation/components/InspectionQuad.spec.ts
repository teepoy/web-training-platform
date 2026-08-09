import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ScSampleTableFilter } from "@/features/sc/domain/sampleTable";
import type { ScGlobalFilter } from "@/features/sc/domain/globalFilter";
import type { ScSampleTableDataSource } from "@/features/sc/domain/workbenchInteraction";
import { mountWithProviders } from "@/testing";
import InspectionQuad from "./InspectionQuad.vue";

const harness = vi.hoisted(() => ({
  options: null as {
    globalFilter: { value: ScGlobalFilter };
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
  mapError: { value: null as string | null },
  mapProgressMessage: { value: "" },
  mapProgressPercent: { value: 0 },
  retryMap: vi.fn(async () => undefined),
  sampleTableDataSource: { value: undefined as ScSampleTableDataSource | undefined },
  galleryLoading: { value: false },
  galleryQuery: { value: {} },
  mapSelectedDefectIds: { value: [] as number[] },
  reviewMode: { value: false },
  tableSelection: { value: { kind: "ids", ids: [] } },
  loadGlobalDistinctValues: vi.fn(async () => []),
  loadGlobalNumericRange: vi.fn(async () => null),
  setTableSelection: vi.fn(),
  setReviewMode: vi.fn(),
  queryBoxSelection: vi.fn(async () => []),
  queryLassoSelection: vi.fn(async () => []),
  queryLegendSelection: vi.fn(async () => []),
  queryAllMapSelection: vi.fn(async () => []),
  queryVisibleMapSelection: vi.fn(async () => []),
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
      "mapSelectionCount",
      "waferGeometry",
      "highlightDefectIds",
      "immediateCrosshairDefectIds",
      "selectionResetVersion",
      "mapError",
    ],
    emits: [
      "update:activeMapTab",
      "update:reticleOptions",
      "zoom-in",
      "legend-group-change",
      "legend-hidden-change",
      "legend-select",
      "commit-map-selection-filter",
      "invert-map-selection-mode",
      "copy-selected-defect-ids",
      "box-select",
      "retry",
    ],
    template: "<div />",
  },
}));
vi.mock("./ScGlobalFilterModal.vue", () => ({
  default: {
    name: "ScGlobalFilterModal",
    props: ["show", "filter", "distinctValues", "numericRanges", "numericRangeLoading", "resetKey"],
    emits: ["update:show", "update:filter", "search-options", "request-range"],
    template: "<div />",
  },
}));
vi.mock("./ScSampleTable.vue", () => ({
  default: {
    name: "ScSampleTable",
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
    model.mapSelectedDefectIds.value = [];
    model.reviewMode.value = false;
    model.mapError.value = null;
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

    filterModal.vm.$emit("request-range", { field: "area", itemId: "area-item" });

    await vi.waitFor(() => {
      expect(filterModal.props("numericRanges")).toEqual({
        "area-item": { min: 1.25, max: 98.5 },
      });
    });
    expect(model.loadGlobalNumericRange).toHaveBeenCalledWith("area", "area-item");
    expect(filterModal.props("numericRangeLoading")).toEqual({ "area-item": false });
  });

  it("owns filter updates and exposes only a cloned workflow snapshot", async () => {
    const { wrapper } = await mountWithProviders(InspectionQuad, {
      props: requiredProps,
    });
    const filter: ScGlobalFilter = {
      combinator: "and",
      items: [
        {
          id: "rough-bin",
          field: "rough_bin",
          condition: { filterType: "set", values: [1, 2] },
          source: { kind: "manual" },
        },
      ],
    };

    const filterModal = wrapper.findComponent({ name: "ScGlobalFilterModal" });
    expect(filterModal.props("show")).toBe(false);
    await wrapper.get("button").trigger("click");
    expect(filterModal.props("show")).toBe(true);

    filterModal.vm.$emit("update:filter", filter);
    await wrapper.vm.$nextTick();

    expect(harness.options?.globalFilter.value).toEqual(filter);
    const exposed = wrapper.vm as unknown as {
      getGlobalFilter: () => ScGlobalFilter;
    };
    const snapshot = exposed.getGlobalFilter();
    expect(snapshot).toEqual(filter);
    const condition = snapshot.items[0]?.condition;
    if (condition?.filterType === "set") condition.values.push(99);
    expect(exposed.getGlobalFilter()).toEqual(filter);
    expect(wrapper.emitted("update:global-filter")).toBeUndefined();
  });

  it("accepts an outer Global Filter model and emits controlled updates", async () => {
    const initialFilter: ScGlobalFilter = {
      combinator: "and",
      items: [
        {
          id: "rough-bin",
          field: "rough_bin",
          condition: { filterType: "set", values: [1] },
          source: { kind: "manual" },
        },
      ],
    };
    const updatedFilter: ScGlobalFilter = {
      combinator: "and",
      items: [
        {
          id: "rough-bin",
          field: "rough_bin",
          condition: { filterType: "set", values: [2, 3] },
          source: { kind: "manual" },
        },
      ],
    };
    const { wrapper } = await mountWithProviders(InspectionQuad, {
      props: { ...requiredProps, globalFilter: initialFilter },
    });

    expect(harness.options?.globalFilter.value).toEqual(initialFilter);
    wrapper.findComponent({ name: "ScGlobalFilterModal" }).vm.$emit("update:filter", updatedFilter);
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted("update:globalFilter")?.[0]?.[0]).toEqual(updatedFilter);
    expect(harness.options?.globalFilter.value).toEqual(initialFilter);

    await wrapper.setProps({ globalFilter: updatedFilter });
    expect(harness.options?.globalFilter.value).toEqual(updatedFilter);
    expect(wrapper.get('[data-testid="sc-global-filter-trigger"]').text()).toBe(
      "Global Filter (1)",
    );
  });

  it("counts complete conditions inside nested Global Filter groups", async () => {
    const { wrapper } = await mountWithProviders(InspectionQuad, {
      props: requiredProps,
    });

    wrapper.findComponent({ name: "ScGlobalFilterModal" }).vm.$emit("update:filter", {
      combinator: "and",
      items: [
        {
          kind: "group",
          id: "class-options",
          combinator: "or",
          items: [
            {
              id: "class-two",
              field: "class_number",
              condition: { filterType: "set", values: [2] },
              source: { kind: "manual" },
            },
            {
              id: "class-three",
              field: "class_number",
              condition: { filterType: "set", values: [3] },
              source: { kind: "manual" },
            },
          ],
        },
      ],
    });
    await wrapper.vm.$nextTick();

    expect(wrapper.get('[data-testid="sc-global-filter-trigger"]').text()).toBe(
      "Global Filter (2)",
    );
  });

  it("retries only the failed map query from the map error action", async () => {
    const { wrapper } = await mountWithProviders(InspectionQuad, {
      props: requiredProps,
    });

    wrapper.findComponent({ name: "ScMapPanelBinned" }).vm.$emit("retry");
    await wrapper.vm.$nextTick();

    expect(model.retryMap).toHaveBeenCalledOnce();
  });

  it("passes the original map query error to the error surface", async () => {
    model.mapError.value = 'DuckDB Binder Error: Referenced column "row_key" not found';
    const { wrapper } = await mountWithProviders(InspectionQuad, {
      props: requiredProps,
    });

    expect(wrapper.findComponent({ name: "ScMapPanelBinned" }).props("mapError")).toBe(
      model.mapError.value,
    );
  });

  it("clears local filter state when the inspection scope changes", async () => {
    const { wrapper } = await mountWithProviders(InspectionQuad, {
      props: requiredProps,
    });
    wrapper.findComponent({ name: "ScGlobalFilterModal" }).vm.$emit("update:filter", {
      combinator: "and",
      items: [
        {
          id: "class-filter",
          field: "class_number",
          condition: { filterType: "set", values: [7] },
          source: { kind: "manual" },
        },
      ],
    });
    await wrapper.vm.$nextTick();

    await wrapper.setProps({ inspectionTime: "2026-07-27T04:00:00+08:00" });

    expect(harness.options?.globalFilter.value).toEqual({ combinator: "and", items: [] });
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
    const table = wrapper.findComponent({ name: "ScSampleTable" });
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

    wrapper.findComponent({ name: "ScSampleTable" }).vm.$emit("selection-change", {
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

  it("keeps map selection and active sampling as composable local filters", async () => {
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
    expect(wrapper.emitted("clear-gallery-random-sampling")).toBeUndefined();
  });

  it("prunes transient map selection when legend values are hidden", async () => {
    model.mapSelectedDefectIds.value = [103, 274];
    model.queryVisibleMapSelection.mockResolvedValueOnce([103]);
    const { wrapper } = await mountWithProviders(InspectionQuad, { props: requiredProps });
    const map = wrapper.findComponent({ name: "ScMapPanelBinned" });
    const initialSelectionResetVersion = map.props("selectionResetVersion");

    map.vm.$emit("legend-hidden-change", { source: "class", hiddenKeys: ["7"] });

    await vi.waitFor(() => {
      expect(model.queryVisibleMapSelection).toHaveBeenCalledWith([103, 274], ["7"]);
      expect(model.applyMapSelection).toHaveBeenCalledWith([103]);
    });
    expect(map.props("selectionResetVersion")).toBe(initialSelectionResetVersion + 1);
  });

  it("does not restore pruned IDs when a legend value is quickly unhidden", async () => {
    let resolveHiddenPrune!: (ids: number[]) => void;
    model.mapSelectedDefectIds.value = [103, 274];
    model.queryVisibleMapSelection
      .mockImplementationOnce(
        () => new Promise<number[]>((resolve) => (resolveHiddenPrune = resolve)),
      )
      .mockResolvedValueOnce([103]);
    model.applyMapSelection
      .mockImplementationOnce(async (ids: number[]) => {
        model.mapSelectedDefectIds.value = [...ids];
      })
      .mockImplementationOnce(async (ids: number[]) => {
        model.mapSelectedDefectIds.value = [...ids];
      });
    const { wrapper } = await mountWithProviders(InspectionQuad, { props: requiredProps });
    const map = wrapper.findComponent({ name: "ScMapPanelBinned" });

    map.vm.$emit("legend-hidden-change", { source: "class", hiddenKeys: ["7"] });
    await vi.waitFor(() => {
      expect(model.queryVisibleMapSelection).toHaveBeenCalledWith([103, 274], ["7"]);
    });

    map.vm.$emit("legend-hidden-change", { source: "class", hiddenKeys: [] });
    await wrapper.vm.$nextTick();
    expect(model.queryVisibleMapSelection).toHaveBeenCalledTimes(1);

    resolveHiddenPrune([103]);
    await vi.waitFor(() => {
      expect(model.queryVisibleMapSelection).toHaveBeenNthCalledWith(2, [103], []);
      expect(model.mapSelectedDefectIds.value).toEqual([103]);
    });
    expect(model.applyMapSelection).not.toHaveBeenCalledWith([103, 274]);
  });

  it("waits for visibility changes queued while a context commit is pending", async () => {
    let resolveHiddenPrune!: (ids: number[]) => void;
    let resolveUnhiddenPrune!: (ids: number[]) => void;
    model.mapSelectedDefectIds.value = [103, 274];
    model.queryVisibleMapSelection
      .mockImplementationOnce(
        () => new Promise<number[]>((resolve) => (resolveHiddenPrune = resolve)),
      )
      .mockImplementationOnce(
        () => new Promise<number[]>((resolve) => (resolveUnhiddenPrune = resolve)),
      );
    model.applyMapSelection
      .mockImplementationOnce(async (ids: number[]) => {
        model.mapSelectedDefectIds.value = [...ids];
      })
      .mockImplementationOnce(async (ids: number[]) => {
        model.mapSelectedDefectIds.value = [...ids];
      });
    const { wrapper } = await mountWithProviders(InspectionQuad, { props: requiredProps });
    const map = wrapper.findComponent({ name: "ScMapPanelBinned" });

    map.vm.$emit("legend-hidden-change", { source: "class", hiddenKeys: ["7"] });
    await vi.waitFor(() => expect(model.queryVisibleMapSelection).toHaveBeenCalledTimes(1));
    map.vm.$emit("commit-map-selection-filter", "exclude");
    map.vm.$emit("legend-hidden-change", { source: "class", hiddenKeys: [] });

    resolveHiddenPrune([103]);
    await vi.waitFor(() => {
      expect(model.queryVisibleMapSelection).toHaveBeenNthCalledWith(2, [103], []);
    });
    expect(harness.options?.globalFilter.value.items).toHaveLength(0);

    resolveUnhiddenPrune([103]);
    await vi.waitFor(() => {
      expect(harness.options?.globalFilter.value.items[0]).toMatchObject({
        field: "defect_id",
        condition: { filterType: "set", values: [103], exclude: true },
      });
    });
  });

  it("does not overwrite a concurrent visible replacement selection with a stale prune", async () => {
    let resolveHiddenPrune!: (ids: number[]) => void;
    model.mapSelectedDefectIds.value = [103, 274];
    model.queryVisibleMapSelection
      .mockImplementationOnce(
        () => new Promise<number[]>((resolve) => (resolveHiddenPrune = resolve)),
      )
      .mockResolvedValueOnce([936]);
    model.queryLegendSelection.mockResolvedValueOnce([936]);
    model.applyMapSelection
      .mockImplementationOnce(async (ids: number[]) => {
        model.mapSelectedDefectIds.value = [...ids];
      })
      .mockImplementationOnce(async (ids: number[]) => {
        model.mapSelectedDefectIds.value = [...ids];
      });
    const { wrapper } = await mountWithProviders(InspectionQuad, { props: requiredProps });
    const map = wrapper.findComponent({ name: "ScMapPanelBinned" });

    map.vm.$emit("legend-hidden-change", { source: "class", hiddenKeys: ["7"] });
    await vi.waitFor(() => expect(model.queryVisibleMapSelection).toHaveBeenCalledTimes(1));
    map.vm.$emit("legend-select", 8);
    await vi.waitFor(() => {
      expect(model.queryLegendSelection).toHaveBeenCalledWith(8, ["7"]);
      expect(model.mapSelectedDefectIds.value).toEqual([936]);
    });

    resolveHiddenPrune([103]);
    await vi.waitFor(() => {
      expect(model.queryVisibleMapSelection).toHaveBeenNthCalledWith(2, [936], ["7"]);
      expect(model.mapSelectedDefectIds.value).toEqual([936]);
    });
    expect(model.applyMapSelection).not.toHaveBeenCalledWith([103]);
  });

  it("discards a pending visibility prune when the workbench scope changes", async () => {
    let resolveHiddenPrune!: (ids: number[]) => void;
    model.mapSelectedDefectIds.value = [103, 274];
    model.queryVisibleMapSelection.mockImplementationOnce(
      () => new Promise<number[]>((resolve) => (resolveHiddenPrune = resolve)),
    );
    const { wrapper } = await mountWithProviders(InspectionQuad, { props: requiredProps });
    const map = wrapper.findComponent({ name: "ScMapPanelBinned" });

    map.vm.$emit("legend-hidden-change", { source: "class", hiddenKeys: ["7"] });
    await vi.waitFor(() => expect(model.queryVisibleMapSelection).toHaveBeenCalledTimes(1));
    await wrapper.setProps({ inspectionTime: "2026-07-27T04:00:00+08:00" });
    expect(model.clearMapSelection).toHaveBeenCalledOnce();

    resolveHiddenPrune([103]);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(model.applyMapSelection).not.toHaveBeenCalled();
  });

  it("cancels a waiting context commit when the workbench unmounts", async () => {
    let resolveHiddenPrune!: (ids: number[]) => void;
    model.mapSelectedDefectIds.value = [103, 274];
    model.queryVisibleMapSelection.mockImplementationOnce(
      () => new Promise<number[]>((resolve) => (resolveHiddenPrune = resolve)),
    );
    const { wrapper } = await mountWithProviders(InspectionQuad, { props: requiredProps });
    const map = wrapper.findComponent({ name: "ScMapPanelBinned" });

    map.vm.$emit("legend-hidden-change", { source: "class", hiddenKeys: ["7"] });
    await vi.waitFor(() => expect(model.queryVisibleMapSelection).toHaveBeenCalledTimes(1));
    map.vm.$emit("commit-map-selection-filter", "exclude");
    wrapper.unmount();

    resolveHiddenPrune([103]);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(harness.options?.globalFilter.value.items).toHaveLength(0);
  });

  it("appends repeated map exclusions as independent Global Filter items", async () => {
    model.mapSelectedDefectIds.value = [103, 274];
    const { wrapper } = await mountWithProviders(InspectionQuad, {
      props: {
        ...requiredProps,
        galleryRandomSamplingDefectIds: new Set(["103", "274"]),
      },
    });

    const map = wrapper.findComponent({ name: "ScMapPanelBinned" });
    const initialSelectionResetVersion = map.props("selectionResetVersion");
    map.vm.$emit("commit-map-selection-filter", "exclude");
    await vi.waitFor(() => {
      expect(harness.options?.globalFilter.value.items).toHaveLength(1);
      expect(model.clearMapSelection).toHaveBeenCalledOnce();
    });

    const firstFilter = harness.options?.globalFilter.value;
    expect(firstFilter?.items).toHaveLength(1);
    expect(firstFilter?.items[0]).toMatchObject({
      field: "defect_id",
      condition: { filterType: "set", values: [103, 274], exclude: true },
      source: { kind: "map-selection", action: "exclude-selected" },
    });
    expect(map.props("selectionResetVersion")).toBe(initialSelectionResetVersion + 1);
    expect(wrapper.emitted("clear-gallery-random-sampling")).toBeUndefined();

    model.mapSelectedDefectIds.value = [274, 936];
    map.vm.$emit("commit-map-selection-filter", "exclude");
    await vi.waitFor(() => expect(harness.options?.globalFilter.value.items).toHaveLength(2));

    const secondFilter = harness.options?.globalFilter.value;
    expect(secondFilter?.items).toHaveLength(2);
    expect(secondFilter?.items.map((item) => item.condition)).toEqual([
      { filterType: "set", values: [103, 274], exclude: true },
      { filterType: "set", values: [274, 936], exclude: true },
    ]);
    expect(secondFilter?.items[0]?.id).not.toBe(secondFilter?.items[1]?.id);
  });

  it("does not restore a slow area selection after committing the current selection", async () => {
    let resolveBoxSelection!: (ids: number[]) => void;
    model.queryBoxSelection.mockImplementationOnce(
      () => new Promise<number[]>((resolve) => (resolveBoxSelection = resolve)),
    );
    model.mapSelectedDefectIds.value = [103];
    const { wrapper } = await mountWithProviders(InspectionQuad, {
      props: requiredProps,
    });
    const map = wrapper.findComponent({ name: "ScMapPanelBinned" });

    map.vm.$emit("box-select", { x: 0, y: 0, w: 10, h: 10 });
    await vi.waitFor(() => expect(model.queryBoxSelection).toHaveBeenCalledOnce());

    map.vm.$emit("commit-map-selection-filter", "exclude");
    await vi.waitFor(() => expect(model.clearMapSelection).toHaveBeenCalledOnce());

    resolveBoxSelection([274]);
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(model.appendMapSelection).not.toHaveBeenCalled();
    expect(harness.options?.globalFilter.value.items[0]).toMatchObject({
      field: "defect_id",
      condition: { filterType: "set", values: [103], exclude: true },
    });
  });

  it("inverts the transient selection within the current Global Filter scope", async () => {
    model.mapSelectedDefectIds.value = [3, 7];
    model.queryAllMapSelection.mockResolvedValue([1, 3, 7, 9]);
    const { wrapper } = await mountWithProviders(InspectionQuad, { props: requiredProps });

    wrapper.findComponent({ name: "ScMapPanelBinned" }).vm.$emit("invert-map-selection-mode");

    await vi.waitFor(() => expect(model.applyMapSelection).toHaveBeenCalledWith([1, 9]));
    expect(model.clearMapSelection).not.toHaveBeenCalled();
  });

  it("copies selected map defect IDs as newline-delimited text", async () => {
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    model.mapSelectedDefectIds.value = [103, 274];
    const { wrapper } = await mountWithProviders(InspectionQuad, {
      props: requiredProps,
    });

    wrapper.findComponent({ name: "ScMapPanelBinned" }).vm.$emit("copy-selected-defect-ids");

    await vi.waitFor(() => expect(writeText).toHaveBeenCalledWith("103\n274"));
  });

  it("composes Review mode with an active sampling cohort", async () => {
    const { wrapper } = await mountWithProviders(InspectionQuad, {
      props: {
        ...requiredProps,
        galleryRandomSamplingDefectIds: new Set(["103"]),
      },
    });

    wrapper.findComponent({ name: "ScBlinkVirtualTable" }).vm.$emit("mode-change", "review");

    expect(model.setReviewMode).toHaveBeenCalledWith(true);
    expect(wrapper.emitted("clear-gallery-random-sampling")).toBeUndefined();
  });
});
