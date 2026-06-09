import { describe, it, expect } from "vitest";
import { mountWithProviders } from "@/testing";

import ScReticleMap from "../ScReticleMap.vue";
import { EMPTY_POINTS, SINGLE_POINT, makeStride6Points } from "./scMapFixtures";

const baseProps = {
  xDieCount: 3,
  yDieCount: 2,
  dieSizeX: 100,
  dieSizeY: 50,
};

describe("ScReticleMap", () => {
  it("shows empty state when no points", async () => {
    const { wrapper } = await mountWithProviders(ScReticleMap, {
      props: {
        ...baseProps,
        points: EMPTY_POINTS,
      },
    });

    expect(wrapper.find(".srm-empty").exists()).toBe(true);
    expect(wrapper.find(".srm-empty").text()).toBe("No points");
  });

  it("renders chart when points are provided", async () => {
    const { wrapper } = await mountWithProviders(ScReticleMap, {
      props: {
        ...baseProps,
        points: SINGLE_POINT,
      },
    });

    await wrapper.vm.$nextTick();
    expect(wrapper.find(".srm-empty").exists()).toBe(false);
    expect(wrapper.find(".srm-canvas").exists()).toBe(true);
  });

  it("renders exactly 10 points when 10 STRIDE=6 points are provided", async () => {
    const points = makeStride6Points(10);
    const { wrapper } = await mountWithProviders(ScReticleMap, {
      props: {
        ...baseProps,
        points,
      },
    });

    await wrapper.vm.$nextTick();
    expect(wrapper.find(".srm-empty").exists()).toBe(false);

    const footerText = wrapper.find(".srm-footer").text();
    expect(footerText).toContain("10 points");
  });

  it("renders reticle grid lines natively", async () => {
    const { wrapper } = await mountWithProviders(ScReticleMap, {
      props: {
        ...baseProps,
        points: SINGLE_POINT,
      },
    });

    await wrapper.vm.$nextTick();
    expect(wrapper.find(".srm-canvas").exists()).toBe(true);
  });

  it("handles invalid die sizes gracefully", async () => {
    const { wrapper } = await mountWithProviders(ScReticleMap, {
      props: {
        ...baseProps,
        dieSizeX: 0,
        dieSizeY: -1,
        points: SINGLE_POINT,
      },
    });

    await wrapper.vm.$nextTick();
    expect(wrapper.find(".srm-canvas").exists()).toBe(true);
  });

  it("renders overlay canvas for interaction", async () => {
    const points = [10, 10, 401, 1, 0, 0];
    const { wrapper } = await mountWithProviders(ScReticleMap, {
      props: {
        ...baseProps,
        points,
      },
    });

    await wrapper.vm.$nextTick();
    // Overlay canvas for drag/zoom interaction
    expect(wrapper.find(".srm-ol").exists()).toBe(true);
    // Main chart canvas still renders
    expect(wrapper.find(".srm-canvas").exists()).toBe(true);
  });

  it("handles pointer events on overlay canvas without crashing", async () => {
    const { wrapper } = await mountWithProviders(ScReticleMap, {
      props: {
        ...baseProps,
        points: SINGLE_POINT,
      },
    });

    await wrapper.vm.$nextTick();
    const overlay = wrapper.find(".srm-ol");

    await overlay.trigger("pointerdown", { clientX: 50, clientY: 50, button: 0 });
    await overlay.trigger("pointermove", { clientX: 100, clientY: 100 });
    await overlay.trigger("pointerup", { clientX: 100, clientY: 100 });

    expect(wrapper.find(".srm-canvas").exists()).toBe(true);
  });
});
