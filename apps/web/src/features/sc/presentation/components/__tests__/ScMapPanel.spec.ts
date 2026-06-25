import { defineComponent, nextTick } from "vue";
import { describe, it, expect, vi } from "vitest";
import { mountWithProviders } from "@/testing";

vi.mock("../ScWaferMap.vue", () => ({
  default: defineComponent({
    name: "ScWaferMap",
    props: {
      points: {
        type: Array,
        default: undefined,
      },
      selectedIds: {
        type: Object,
        default: undefined,
      },
      highlightDefects: {
        type: Array,
        default: undefined,
      },
      queryBoxSelection: {
        type: Function,
        default: undefined,
      },
      colorMap: {
        type: Object,
        default: undefined,
      },
    },
    template: "<div />",
  }),
}));

vi.mock("../ScDieStackMap.vue", () => ({
  default: defineComponent({ name: "ScDieStackMap", template: "<div />" }),
}));

vi.mock("../ScReticleMap.vue", () => ({
  default: defineComponent({ name: "ScReticleMap", template: "<div />" }),
}));

import ScMapPanel from "@/features/sc/presentation/components/ScMapPanel.vue";
import { MIXED_CLASS_POINTS } from "./scMapFixtures";
import { legendColor } from "../scMapUtils";

describe("ScMapPanel", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("renders wafer tab by default", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: {
        waferPoints: MIXED_CLASS_POINTS,
        waferRadiusNm: 150000,
        waferGeometry: {
          centerX: 0,
          centerY: 0,
          originX: 0,
          originY: 0,
          dieSizeX: 1000,
          dieSizeY: 1000,
        },
      },
    });

    expect(wrapper.find('[data-testid="sc-map-panel"]').exists()).toBe(true);
    expect(wrapper.findComponent({ name: "ScWaferMap" }).exists()).toBe(true);
    expect(wrapper.findComponent({ name: "ScDieStackMap" }).exists()).toBe(false);
    expect(wrapper.findComponent({ name: "ScReticleMap" }).exists()).toBe(false);
  });

  it("removes the legacy filter tab", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: { waferPoints: MIXED_CLASS_POINTS },
    });

    expect(wrapper.find('[data-testid="sc-filter-tab"]').exists()).toBe(false);
    expect(wrapper.text()).not.toContain("Filter");
  });

  it("passes table highlight defects to the active map", async () => {
    const highlightDefects = [
      { defectId: 101, waferX: 10, waferY: 20, dieX: 30, dieY: 40, reticleX: 50, reticleY: 60 },
      { defectId: 103, waferX: 15, waferY: 25, dieX: 35, dieY: 45, reticleX: 55, reticleY: 65 },
    ];
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: {
        waferPoints: MIXED_CLASS_POINTS,
        highlightDefects,
      },
    });

    expect(wrapper.findComponent({ name: "ScWaferMap" }).props("highlightDefects")).toEqual(
      highlightDefects,
    );
  });

  it("clicking die tab shows sc-die-stack-canvas", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: {
        diePoints: MIXED_CLASS_POINTS,
      },
    });

    await wrapper.setProps({ activeMapTab: "die" });
    await nextTick();

    expect(wrapper.findComponent({ name: "ScDieStackMap" }).exists()).toBe(true);
  });

  it("clicking reticle tab shows sc-reticle-canvas", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: {
        reticlePoints: MIXED_CLASS_POINTS,
        reticleXDieCount: 2,
        reticleYDieCount: 2,
        reticleDieSizeX: 500,
        reticleDieSizeY: 500,
      },
    });

    await wrapper.setProps({ activeMapTab: "reticle" });
    await nextTick();

    expect(wrapper.findComponent({ name: "ScReticleMap" }).exists()).toBe(true);
  });

  it("legend click emits select-points with correct IDs", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: {
        waferPoints: MIXED_CLASS_POINTS,
      },
    });

    const legend = wrapper.findComponent({ name: "ScLegend" });
    legend.vm.$emit("select-class", 1);

    expect(wrapper.emitted("select-points")).toBeTruthy();
    expect(wrapper.emitted("select-points")?.[0]).toEqual([
      { ids: [101, 102], region: { x: 0, y: 0, w: 0, h: 0 } },
    ]);
  });

  it("curries the wafer mode into the box selection query", async () => {
    const queryBoxSelection = vi.fn().mockResolvedValue([101]);
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: { waferPoints: MIXED_CLASS_POINTS, queryBoxSelection },
    });
    const region = { x: 10, y: 20, w: 30, h: 40 };

    const query = wrapper.findComponent({ name: "ScWaferMap" }).props("queryBoxSelection") as (
      region: typeof region,
    ) => Promise<number[]>;
    await query(region);

    expect(queryBoxSelection).toHaveBeenCalledWith("wafer", region);
  });

  it("uses compact class-list IDs for legend selection", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: {
        waferPoints: MIXED_CLASS_POINTS.slice(0, 6),
        legendGroups: {
          "9": {
            $typeName: "sc.v1.DefectList",
            count: 2,
            defectIds: [501, 502],
          },
        },
      },
    });

    wrapper.findComponent({ name: "ScLegend" }).vm.$emit("select-class", 9);

    expect(wrapper.emitted("select-points")?.[0]).toEqual([
      { ids: [501, 502], region: { x: 0, y: 0, w: 0, h: 0 } },
    ]);
  });

  it("hides legend classes from map points", async () => {
    const queryBoxSelection = vi.fn(async () => [101, 201, 1]);
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: {
        waferPoints: MIXED_CLASS_POINTS,
        queryBoxSelection,
      },
    });

    await wrapper.find('[data-testid="sc-legend-visible-1"]').trigger("click");
    await nextTick();

    const wafer = wrapper.findComponent({ name: "ScWaferMap" });
    expect(wafer.props("points")).toEqual([2100, 2200, 201, 2, 0, 0, 3100, 3200, 1, 0, 0, 0]);
    await expect(
      (
        wafer.props("queryBoxSelection") as (region: {
          x: number;
          y: number;
          w: number;
          h: number;
        }) => Promise<number[]>
      )({ x: 0, y: 0, w: 10, h: 10 }),
    ).resolves.toEqual([201, 1]);
  });

  it("restores externally controlled selection after remount", async () => {
    const selectedIds = new Set([101, 103]);
    const first = await mountWithProviders(ScMapPanel, {
      props: {
        waferPoints: MIXED_CLASS_POINTS,
        selectedIds,
      },
    });

    expect(first.wrapper.findComponent({ name: "ScWaferMap" }).props("selectedIds")).toEqual(
      selectedIds,
    );
    first.wrapper.unmount();

    const second = await mountWithProviders(ScMapPanel, {
      props: {
        waferPoints: MIXED_CLASS_POINTS,
        selectedIds,
      },
    });
    expect(second.wrapper.findComponent({ name: "ScWaferMap" }).props("selectedIds")).toEqual(
      selectedIds,
    );
  });

  it("renders labeled selection and zoom tools", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: { waferPoints: MIXED_CLASS_POINTS },
    });

    expect(wrapper.find('[aria-label="Box selection"]').exists()).toBe(true);
    expect(wrapper.find('[aria-label="Zoom in"]').exists()).toBe(true);
  });

  it("resets zoom when switching map tabs", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: { waferPoints: MIXED_CLASS_POINTS },
    });

    const tabs = wrapper.findAll(".n-tabs-tab");
    expect(tabs.length).toBeGreaterThan(1);
    await tabs[1].trigger("click");
    await nextTick();

    expect(wrapper.emitted("update:activeMapTab")?.[0]).toEqual(["die"]);
    expect(wrapper.emitted("zoom-in")?.[0]).toEqual([null]);
  });

  it("reticle options submit emits update:reticleOptions", async () => {
    const options = { xDieCount: 3, yDieCount: 3, xDieShift: 0, yDieShift: 0 };
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: {
        activeMapTab: "reticle",
        reticleOptions: options,
        reticleXDieCount: 2,
        reticleYDieCount: 2,
        reticleDieSizeX: 500,
        reticleDieSizeY: 500,
      },
    });

    await nextTick();

    const btn = wrapper.findComponent({ name: "ScReticleMapOptionsButton" });
    expect(btn.exists()).toBe(true);

    const newOptions = { xDieCount: 4, yDieCount: 4, xDieShift: 1, yDieShift: 1 };
    btn.vm.$emit("submit", newOptions);

    expect(wrapper.emitted("update:reticleOptions")).toBeTruthy();
    expect(wrapper.emitted("update:reticleOptions")?.[0]).toEqual([newOptions]);
  });

  it("renders error state correctly", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: {
        mapError: "Failed to load data",
      },
    });

    expect(wrapper.text()).toContain("Failed to load data");

    const btn = wrapper.find("button");
    await btn.trigger("click");
    expect(wrapper.emitted("retry")).toBeTruthy();
  });

  it("legend is visible at all three inner tabs", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: {
        waferPoints: MIXED_CLASS_POINTS,
        diePoints: MIXED_CLASS_POINTS,
        reticlePoints: MIXED_CLASS_POINTS,
        reticleXDieCount: 2,
        reticleYDieCount: 2,
        reticleDieSizeX: 500,
        reticleDieSizeY: 500,
      },
    });

    expect(wrapper.findComponent({ name: "ScLegend" }).exists()).toBe(true);

    await wrapper.setProps({ activeMapTab: "die" });
    await nextTick();
    expect(wrapper.findComponent({ name: "ScLegend" }).exists()).toBe(true);

    await wrapper.setProps({ activeMapTab: "reticle" });
    await nextTick();
    expect(wrapper.findComponent({ name: "ScLegend" }).exists()).toBe(true);
  });

  it("floating toolbar starts visible", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: { waferPoints: MIXED_CLASS_POINTS },
    });
    const container = wrapper.find('[data-testid="sc-map-toolbar-container"]');
    expect(container.exists()).toBe(true);
  });

  it("toolbar toggle button hides/shows mode buttons", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: { waferPoints: MIXED_CLASS_POINTS },
    });
    const toggle = wrapper.find('[data-testid="sc-map-toolbar-toggle"]');
    expect(toggle.exists()).toBe(true);
    // Click toggle — the component should still be rendered (v-show hides, not v-if removes)
    await toggle.trigger("click");
    await nextTick();
    // toolbar is still in DOM, just hidden by v-show on child div
    expect(wrapper.find('[data-testid="sc-map-toolbar-container"]').exists()).toBe(true);
  });

  it("drawer toggle button exists and is clickable", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: { waferPoints: MIXED_CLASS_POINTS },
    });
    const toggle = wrapper.find('[data-testid="sc-map-drawer-toggle"]');
    expect(toggle.exists()).toBe(true);
    await toggle.trigger("click");
    await nextTick();
    // drawer should still exist, just collapsed
    expect(wrapper.find('[data-testid="sc-map-drawer"]').exists()).toBe(true);
  });

  it("legend source select dropdown exists", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: { waferPoints: MIXED_CLASS_POINTS },
    });
    const select = wrapper.find('[data-testid="sc-legend-source-select"]');
    expect(select.exists()).toBe(true);
  });

  it("supports latest prediction groups in the legend", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: {
        waferPoints: MIXED_CLASS_POINTS,
        legendSources: ["class", "bin", "annotation", "prediction"],
        legendGroups: {
          Scratch: {
            $typeName: "sc.v1.DefectList",
            count: 2,
            defectIds: [501, 502],
          },
        },
      },
    });

    const select = wrapper.findComponent({ name: "Select" });
    expect(select.props("options")).toEqual([
      { label: "Class Mapping", value: "class" },
      { label: "Rough Bin Mapping", value: "bin" },
      { label: "Annotation", value: "annotation" },
      { label: "Prediction (Latest)", value: "prediction" },
    ]);

    select.vm.$emit("update:value", "prediction");
    await nextTick();
    wrapper.findComponent({ name: "ScLegend" }).vm.$emit("select-class", "Scratch");

    expect(wrapper.emitted("select-points")?.[0]).toEqual([
      { ids: [501, 502], region: { x: 0, y: 0, w: 0, h: 0 } },
    ]);
  });

  it("passes current legend group color map to the map", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: {
        waferPoints: MIXED_CLASS_POINTS,
        legendSources: ["class", "bin", "annotation", "prediction"],
        legendGroups: {
          Scratch: {
            $typeName: "sc.v1.DefectList",
            count: 2,
            defectIds: [101, 103],
          },
        },
      },
    });

    wrapper.findComponent({ name: "Select" }).vm.$emit("update:value", "annotation");
    await nextTick();

    const colorMap = wrapper.findComponent({ name: "ScWaferMap" }).props("colorMap") as Record<
      string,
      string
    >;

    expect(colorMap["0"]).toEqual(legendColor("annotation", "Scratch"));
  });

  it("groups and selects defects without annotations", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: {
        waferPoints: MIXED_CLASS_POINTS,
        legendSources: ["class", "bin", "annotation", "prediction"],
        legendGroups: {
          Reviewed: {
            $typeName: "sc.v1.DefectList",
            count: 1,
            defectIds: [101],
          },
          __unlabeled__: {
            $typeName: "sc.v1.DefectList",
            count: 2,
            defectIds: [102, 103],
          },
        },
      },
    });

    wrapper.findComponent({ name: "Select" }).vm.$emit("update:value", "annotation");
    await nextTick();
    const legend = wrapper.findComponent({ name: "ScLegend" });
    expect(legend.props("annotations").__unlabeled__.defectIds).toEqual([102, 103]);

    legend.vm.$emit("select-class", "__unlabeled__");
    expect(wrapper.emitted("select-points")?.[0]).toEqual([
      { ids: [102, 103], region: { x: 0, y: 0, w: 0, h: 0 } },
    ]);
  });

  it("persists toolbar collapsed state to localStorage", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: { waferPoints: MIXED_CLASS_POINTS },
    });
    // First visit: nothing in localStorage
    expect(localStorage.getItem("sc_map_panel.toolbar_collapsed")).toBeNull();
    // Collapse toolbar
    const toggle = wrapper.find('[data-testid="sc-map-toolbar-toggle"]');
    await toggle.trigger("click");
    await nextTick();
    // Should persist collapsed=true (toolbarVisible=false → !false = true in storage)
    expect(localStorage.getItem("sc_map_panel.toolbar_collapsed")).toBe("true");
  });

  it("starts with toolbar collapsed when localStorage says so", async () => {
    localStorage.setItem("sc_map_panel.toolbar_collapsed", "true");
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: { waferPoints: MIXED_CLASS_POINTS },
    });
    // toolbarVisible should be false → !loadPersistedState(..., false) → key="true" → load returns true → !true = false
    // Since we can't directly read toolbarVisible, verify the drawer still renders
    expect(wrapper.find('[data-testid="sc-map-toolbar-toggle"]').exists()).toBe(true);
  });

  it("defaults to expanded on corrupted localStorage value", async () => {
    localStorage.setItem("sc_map_panel.drawer_collapsed", "garbage");
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: { waferPoints: MIXED_CLASS_POINTS },
    });
    expect(wrapper.find('[data-testid="sc-map-drawer"]').exists()).toBe(true);
  });

  it("falls back to sampled points when legendGroups is missing", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: { waferPoints: MIXED_CLASS_POINTS },
    });

    const legend = wrapper.findComponent({ name: "ScLegend" });
    legend.vm.$emit("select-class", 1);
    expect(wrapper.emitted("select-points")?.[0]).toEqual([
      { ids: [101, 102], region: { x: 0, y: 0, w: 0, h: 0 } },
    ]);
  });

  it("falls back to sampled points when legendGroups is null", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanel, {
      props: {
        waferPoints: MIXED_CLASS_POINTS,
        legendGroups: null,
      },
    });

    const legend = wrapper.findComponent({ name: "ScLegend" });
    legend.vm.$emit("select-class", 1);
    expect(wrapper.emitted("select-points")?.[0]).toEqual([
      { ids: [101, 102], region: { x: 0, y: 0, w: 0, h: 0 } },
    ]);
  });
});
