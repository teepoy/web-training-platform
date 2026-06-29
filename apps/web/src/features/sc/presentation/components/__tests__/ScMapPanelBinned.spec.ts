import { defineComponent } from "vue";
import { describe, it, expect, vi } from "vitest";
import { mountWithProviders } from "@/testing";
import ScMapPanelBinned from "../ScMapPanelBinned.vue";

vi.mock("../ScWaferMapPerspective.vue", () => ({
  default: defineComponent({
    name: "ScWaferMapPerspective",
    props: {
      points: Array,
      geometry: Object,
      waferRadiusNm: Number,
      colorMap: Object,
      zoom: Object,
      mode: String,
      queryBoxSelection: Function,
      highlightDefects: Array,
    },
    template: "<div data-testid='wafer-map' />",
  }),
}));
vi.mock("../ScDieStackMapPerspective.vue", () => ({
  default: defineComponent({
    name: "ScDieStackMapPerspective",
    props: {
      points: Array,
      colorMap: Object,
      zoom: Object,
      mode: String,
      queryBoxSelection: Function,
      highlightDefects: Array,
    },
    template: "<div data-testid='die-map' />",
  }),
}));
vi.mock("../ScReticleMapPerspective.vue", () => ({
  default: defineComponent({
    name: "ScReticleMapPerspective",
    props: {
      points: Array,
      colorMap: Object,
      zoom: Object,
      mode: String,
      queryBoxSelection: Function,
      highlightDefects: Array,
    },
    template: "<div data-testid='reticle-map' />",
  }),
}));

describe("ScMapPanelBinned — highlightDefects prop", () => {
  it("passes highlightDefects to the active wafer child map", async () => {
    const hd = [
      { defectId: 1, waferX: 100, waferY: 200, dieX: 10, dieY: 20, reticleX: 1, reticleY: 2 },
    ];
    const { wrapper } = await mountWithProviders(ScMapPanelBinned, {
      props: {
        activeMapTab: "wafer",
        highlightDefects: hd,
        waferGeometry: {
          centerX: 0,
          centerY: 0,
          originX: -1000,
          originY: -1000,
          dieSizeX: 100,
          dieSizeY: 100,
        },
      },
    });
    const waferMap = wrapper.findComponent({ name: "ScWaferMapPerspective" });
    expect(waferMap.exists()).toBe(true);
    expect(waferMap.props("highlightDefects")).toEqual(hd);
  });

  it("renders without error when highlightDefects is undefined", async () => {
    const { wrapper } = await mountWithProviders(ScMapPanelBinned, {
      props: {
        activeMapTab: "wafer",
        waferGeometry: {
          centerX: 0,
          centerY: 0,
          originX: -1000,
          originY: -1000,
          dieSizeX: 100,
          dieSizeY: 100,
        },
      },
    });
    expect(wrapper.exists()).toBe(true);
  });
});
