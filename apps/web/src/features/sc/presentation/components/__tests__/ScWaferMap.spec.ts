import { describe, it, expect, vi, afterEach } from "vitest";
import { mountWithProviders } from "@/testing";
import { SINGLE_POINT, EMPTY_POINTS, makeStride6Points } from "./scMapFixtures";
import { truncatePoints, STRIDE } from "../scMapUtils";
import ScWaferMap from "../ScWaferMap.vue";

vi.stubGlobal("ResizeObserver", class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
});

Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, value: 600 });
Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, value: 600 });
Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
  configurable: true,
  value: () => ({ left: 0, top: 0, width: 600, height: 600 }),
});

const smallGeometry = {
  centerX: 0,
  centerY: 0,
  originX: 0,
  originY: 0,
  dieSizeX: 500,
  dieSizeY: 500,
};

const smallRadius = 5000;

describe("ScWaferMap", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows empty state when no points", async () => {
    const { wrapper } = await mountWithProviders(ScWaferMap, {
      props: { points: undefined, geometry: smallGeometry, waferRadiusNm: smallRadius },
    });
    expect(wrapper.find(".swm-empty").exists()).toBe(true);
    expect(wrapper.find(".swm-empty").text()).toBe("No points");
  });

  it("shows empty state when points array is empty", async () => {
    const { wrapper } = await mountWithProviders(ScWaferMap, {
      props: { points: EMPTY_POINTS, geometry: smallGeometry, waferRadiusNm: smallRadius },
    });
    expect(wrapper.find(".swm-empty").exists()).toBe(true);
  });

  it("renders canvas when points are provided", async () => {
    const { wrapper } = await mountWithProviders(ScWaferMap, {
      props: { points: SINGLE_POINT, geometry: smallGeometry, waferRadiusNm: smallRadius },
    });
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".swm-empty").exists()).toBe(false);
    expect(wrapper.find(".swm-canvas").exists()).toBe(true);
  });

  it("shows correct point count in footer", async () => {
    const points = makeStride6Points(3);
    const { wrapper } = await mountWithProviders(ScWaferMap, {
      props: { points, geometry: smallGeometry, waferRadiusNm: smallRadius },
    });
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".swm-footer").text()).toContain("3 points");
  });

  it("does not crash with zero container dimensions", async () => {
    const origW = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientWidth")!;
    const origH = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientHeight")!;

    Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, value: 0 });
    Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, value: 0 });

    try {
      const { wrapper } = await mountWithProviders(ScWaferMap, {
        props: { points: SINGLE_POINT, geometry: smallGeometry, waferRadiusNm: smallRadius },
      });
      await wrapper.vm.$nextTick();
      expect(wrapper.find(".swm-canvas").exists()).toBe(true);
    } finally {
      Object.defineProperty(HTMLElement.prototype, "clientWidth", origW);
      Object.defineProperty(HTMLElement.prototype, "clientHeight", origH);
    }
  });

  it("truncatePoints truncates correctly above MAX_RENDERED_POINTS", () => {
    const points = makeStride6Points(10);
    const { truncated, wasTruncated } = truncatePoints(points, 3);

    expect(wasTruncated).toBe(true);
    expect(truncated.length).toBe(3 * STRIDE);
    expect(truncated[2]).toBe(points[2]);
  });

  it("truncatePoints does not truncate when under max", () => {
    const points = makeStride6Points(5);
    const { truncated, wasTruncated } = truncatePoints(points, 10);

    expect(wasTruncated).toBe(false);
    expect(truncated).toBe(points);
  });

  it("truncatePoints returns empty when max=0", () => {
    const points = makeStride6Points(3);
    const { truncated, wasTruncated } = truncatePoints(points, 0);

    expect(wasTruncated).toBe(true);
    expect(truncated).toHaveLength(0);
  });
});
