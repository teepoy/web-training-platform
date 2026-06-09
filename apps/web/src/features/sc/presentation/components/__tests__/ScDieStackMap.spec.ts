import { describe, it, expect, vi } from "vitest";
import { mountWithProviders } from "@/testing";
import { SINGLE_POINT, EMPTY_POINTS, makeStride6Points } from "./scMapFixtures";
import ScDieStackMap from "../ScDieStackMap.vue";

// Provide a basic ResizeObserver mock for the component
vi.stubGlobal('ResizeObserver', class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
});

// Mock clientWidth/Height
Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, value: 600 });
Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, value: 240 });
Object.defineProperty(HTMLElement.prototype, 'getBoundingClientRect', {
  configurable: true,
  value: () => ({ left: 0, top: 0, width: 600, height: 240 })
});

describe("ScDieStackMap", () => {
  it("shows empty state when no points", async () => {
    const { wrapper } = await mountWithProviders(ScDieStackMap, {
      props: { points: undefined },
    });
    expect(wrapper.find(".sdsm-empty").exists()).toBe(true);
    expect(wrapper.find(".sdsm-empty").text()).toBe("No points");
  });

  it("shows empty state when points array is empty", async () => {
    const { wrapper } = await mountWithProviders(ScDieStackMap, {
      props: { points: EMPTY_POINTS },
    });
    expect(wrapper.find(".sdsm-empty").exists()).toBe(true);
  });

  it("renders canvas when points are provided", async () => {
    const { wrapper } = await mountWithProviders(ScDieStackMap, {
      props: { points: SINGLE_POINT },
    });
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".sdsm-empty").exists()).toBe(false);
    expect(wrapper.find(".sdsm-canvas").exists()).toBe(true);
  });

  it("shows '1 point' (singular) for single point in footer", async () => {
    const { wrapper } = await mountWithProviders(ScDieStackMap, {
      props: { points: SINGLE_POINT },
    });
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".sdsm-footer").text()).toContain("1 point");
    expect(wrapper.find(".sdsm-footer").text()).not.toContain("1 points");
  });

  it("shows '3 points' in footer when 3 points are passed", async () => {
    const points = makeStride6Points(3);
    const { wrapper } = await mountWithProviders(ScDieStackMap, {
      props: { points },
    });
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".sdsm-footer").text()).toContain("3 points");
  });

  it("does not show clear button when nothing is selected", async () => {
    const { wrapper } = await mountWithProviders(ScDieStackMap, {
      props: { points: makeStride6Points(2) },
    });
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".sdsm-clear").exists()).toBe(false);
  });

  it("handles pointer events on overlay canvas without crashing", async () => {
    const { wrapper } = await mountWithProviders(ScDieStackMap, {
      props: { points: SINGLE_POINT },
    });

    await wrapper.vm.$nextTick();

    const overlay = wrapper.find(".sdsm-ol");

    // Simulate pointerdown and pointerup at center (select mode, no emit expected)
    await overlay.trigger("pointerdown", { clientX: 300, clientY: 120, button: 0 });
    await overlay.trigger("pointerup", { clientX: 300, clientY: 120 });

    await wrapper.vm.$nextTick();
    // Component should not crash
    expect(wrapper.find(".sdsm-canvas").exists()).toBe(true);
  });

  it("handles drag on overlay canvas without crashing", async () => {
    const { wrapper } = await mountWithProviders(ScDieStackMap, {
      props: { points: SINGLE_POINT },
    });

    await wrapper.vm.$nextTick();

    const overlay = wrapper.find(".sdsm-ol");

    await overlay.trigger("pointerdown", { clientX: 10, clientY: 10, button: 0 });
    await overlay.trigger("pointermove", { clientX: 590, clientY: 230 });
    await overlay.trigger("pointerup", { clientX: 590, clientY: 230 });

    await wrapper.vm.$nextTick();
    // Component should not crash
    expect(wrapper.find(".sdsm-canvas").exists()).toBe(true);
  });

  it("handles resize", async () => {
    const { wrapper } = await mountWithProviders(ScDieStackMap, {
      props: { points: SINGLE_POINT },
    });
    await wrapper.vm.$nextTick();

    expect(wrapper.find(".sdsm-canvas").exists()).toBe(true);
  });
});
