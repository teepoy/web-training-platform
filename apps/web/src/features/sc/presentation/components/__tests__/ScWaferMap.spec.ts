import { describe, it, expect, vi, afterEach } from "vitest";
import { nextTick } from "vue";
import { mountWithProviders } from "@/testing";
import { SINGLE_POINT, EMPTY_POINTS, makeStride6Points } from "./scMapFixtures";
import { truncatePoints, STRIDE } from "../scMapUtils";
import ScWaferMap from "../ScWaferMap.vue";
import SimpleWaferMap from "../SimpleWaferMap.vue";

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

const offsetGeometry = {
  centerX: 0,
  centerY: 0,
  originX: -1800000,
  originY: 0,
  dieSizeX: 500,
  dieSizeY: 500,
};

const smallRadius = 5000;

function makeFixedPoints(
  entries: { id: number; classNumber: number }[],
): number[] {
  const result: number[] = [];
  for (let i = 0; i < entries.length; i++) {
    const x = 100 + i * 200;
    const y = 100 + i * 150;
    result.push(x, y, entries[i].id, entries[i].classNumber, 0, 0);
  }
  return result;
}

async function simulateBoxDrag(
  wrapper: ReturnType<typeof mountWithProviders>["wrapper"],
  startX: number,
  startY: number,
  endX: number,
  endY: number,
) {
  const canvas = wrapper.find(".swm-ol");
  await canvas.trigger("pointerdown", { button: 0, clientX: startX, clientY: startY });
  await canvas.trigger("pointermove", { clientX: endX, clientY: endY });
  await canvas.trigger("pointerup", { clientX: endX, clientY: endY });
  await nextTick();
}

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

describe("ScWaferMap selection state", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("does not emit selection-change when selectedIds prop changes", async () => {
    const points = makeFixedPoints([
      { id: 101, classNumber: 1 },
      { id: 102, classNumber: 1 },
      { id: 201, classNumber: 2 },
    ]);

    const { wrapper } = await mountWithProviders(ScWaferMap, {
      props: {
        points,
        geometry: smallGeometry,
        waferRadiusNm: smallRadius,
        selectedIds: new Set(),
      },
    });

    await nextTick();
    const initialEmitCount = wrapper.emitted("selection-change")?.length ?? 0;

    await wrapper.setProps({ selectedIds: new Set([101, 102]) });
    await nextTick();

    const events = wrapper.emitted("selection-change");
    expect(events?.length ?? 0).toBe(initialEmitCount);
  });

  it("unions box drag results with existing selectedIds", async () => {
    const points = makeFixedPoints([
      { id: 101, classNumber: 1 },
      { id: 201, classNumber: 2 },
      { id: 301, classNumber: 0 },
    ]);

    const queryBoxSelection = vi.fn().mockResolvedValue([201]);

    const { wrapper } = await mountWithProviders(ScWaferMap, {
      props: {
        points,
        geometry: smallGeometry,
        waferRadiusNm: smallRadius,
        selectedIds: new Set([101]),
        queryBoxSelection,
      },
    });

    await nextTick();

    await simulateBoxDrag(wrapper, 100, 100, 200, 200);

    expect(queryBoxSelection).toHaveBeenCalled();

    const events = wrapper.emitted("selection-change");
    const lastEmit = events![events!.length - 1][0] as number[];
    expect(lastEmit).toContain(101);
    expect(lastEmit).toContain(201);
  });

  it("accumulates multiple box drags into a single union", async () => {
    const points = makeFixedPoints([
      { id: 101, classNumber: 1 },
      { id: 201, classNumber: 2 },
      { id: 301, classNumber: 0 },
    ]);

    let callCount = 0;
    const queryBoxSelection = vi.fn().mockImplementation(async () => {
      callCount++;
      return callCount === 1 ? [201] : [301];
    });

    const { wrapper } = await mountWithProviders(ScWaferMap, {
      props: {
        points,
        geometry: smallGeometry,
        waferRadiusNm: smallRadius,
        selectedIds: new Set([101]),
        queryBoxSelection,
      },
    });

    await nextTick();

    await simulateBoxDrag(wrapper, 50, 50, 120, 120);
    await simulateBoxDrag(wrapper, 150, 150, 220, 220);

    const events = wrapper.emitted("selection-change");
    const lastEmit = events![events!.length - 1][0] as number[];
    expect(lastEmit).toContain(101);
    expect(lastEmit).toContain(301);
  });

  it("preserves box-selected IDs when selectedIds prop is cleared", async () => {
    const points = makeFixedPoints([
      { id: 101, classNumber: 1 },
      { id: 201, classNumber: 2 },
      { id: 301, classNumber: 0 },
    ]);

    const queryBoxSelection = vi.fn().mockResolvedValue([201]);

    const { wrapper } = await mountWithProviders(ScWaferMap, {
      props: {
        points,
        geometry: smallGeometry,
        waferRadiusNm: smallRadius,
        selectedIds: new Set(),
        queryBoxSelection,
      },
    });

    await nextTick();

    await simulateBoxDrag(wrapper, 100, 100, 200, 200);

    const events = wrapper.emitted("selection-change");
    const lastEmit = events![events!.length - 1][0] as number[];
    expect(lastEmit).not.toContain(101);
    expect(lastEmit).toContain(201);
  });

  it("clears selection on double-click and emits empty array", async () => {
    const points = makeFixedPoints([
      { id: 101, classNumber: 1 },
      { id: 201, classNumber: 2 },
    ]);

    const { wrapper } = await mountWithProviders(ScWaferMap, {
      props: {
        points,
        geometry: smallGeometry,
        waferRadiusNm: smallRadius,
        selectedIds: new Set([101]),
      },
    });

    await nextTick();

    const canvas = wrapper.find(".swm-ol");
    await canvas.trigger("dblclick");
    await nextTick();

    const events = wrapper.emitted("selection-change");
    const lastEmit = events![events!.length - 1][0] as number[];
    expect(lastEmit).toEqual([]);
  });

  it("uses sampled points even when queryBoxSelection is missing", async () => {
    const points = makeFixedPoints([{ id: 101, classNumber: 1 }]);

    const { wrapper } = await mountWithProviders(ScWaferMap, {
      props: {
        points,
        geometry: smallGeometry,
        waferRadiusNm: smallRadius,
        selectedIds: new Set(),
      },
    });

    await nextTick();
    await simulateBoxDrag(wrapper, 300, 288, 312, 300);

    expect(wrapper.emitted("selection-change")?.at(-1)?.[0]).toContain(101);
  });

  it("emits sampled hits before the backend selection resolves", async () => {
    let resolveBackend: ((ids: number[]) => void) | undefined;
    const queryBoxSelection = vi.fn(
      () => new Promise<number[]>((resolve) => {
        resolveBackend = resolve;
      }),
    );
    const points = makeFixedPoints([{ id: 101, classNumber: 1 }]);
    const { wrapper } = await mountWithProviders(ScWaferMap, {
      props: {
        points,
        geometry: smallGeometry,
        waferRadiusNm: smallRadius,
        selectedIds: new Set(),
        queryBoxSelection,
      },
    });

    const canvas = wrapper.find(".swm-ol");
    await canvas.trigger("pointerdown", { button: 0, clientX: 300, clientY: 288 });
    await canvas.trigger("pointermove", { clientX: 312, clientY: 300 });
    const drag = canvas.trigger("pointerup", { clientX: 312, clientY: 300 });
    await nextTick();
    expect(wrapper.emitted("selection-change")?.at(-1)?.[0]).toContain(101);

    resolveBackend?.([201]);
    await drag;
    expect(wrapper.emitted("selection-change")?.at(-1)?.[0]).toEqual(
      expect.arrayContaining([201]),
    );
  });

  it("renders selected points from prop without internal state", async () => {
    const points = makeFixedPoints([
      { id: 101, classNumber: 1 },
      { id: 102, classNumber: 1 },
    ]);

    const { wrapper } = await mountWithProviders(ScWaferMap, {
      props: {
        points,
        geometry: smallGeometry,
        waferRadiusNm: smallRadius,
        selectedIds: new Set([101]),
      },
    });

    await nextTick();

    const simpleWaferMap = wrapper.findComponent(SimpleWaferMap);
    expect(simpleWaferMap.exists()).toBe(true);
    const emittedPoints = simpleWaferMap.props("points") as { isSelectedFlag: boolean }[];
    expect(emittedPoints[0].isSelectedFlag).toBe(true);
    expect(emittedPoints[1].isSelectedFlag).toBe(false);
  });

  it("passes originX/originY props to SimpleWaferMap when geometry has them", async () => {
    const points = makeFixedPoints([{ id: 101, classNumber: 1 }]);

    const { wrapper } = await mountWithProviders(ScWaferMap, {
      props: {
        points,
        geometry: offsetGeometry,
        waferRadiusNm: smallRadius,
        selectedIds: new Set(),
      },
    });

    await nextTick();

    const simpleWaferMap = wrapper.findComponent(SimpleWaferMap);
    expect(simpleWaferMap.props("originX")).toBe(-1800000);
    expect(simpleWaferMap.props("originY")).toBe(0);
  });

  it("passes originX/originY as undefined when geometry omits them", async () => {
    const points = makeFixedPoints([{ id: 101, classNumber: 1 }]);
    const geometryWithoutOrigin = {
      centerX: 0,
      centerY: 0,
      dieSizeX: 500,
      dieSizeY: 500,
    } as any;

    const { wrapper } = await mountWithProviders(ScWaferMap, {
      props: {
        points,
        geometry: geometryWithoutOrigin,
        waferRadiusNm: smallRadius,
        selectedIds: new Set(),
      },
    });

    await nextTick();

    const simpleWaferMap = wrapper.findComponent(SimpleWaferMap);
    expect(simpleWaferMap.props("originX")).toBeUndefined();
    expect(simpleWaferMap.props("originY")).toBeUndefined();
  });

  it("discards stale backend results when double-click clears during in-flight query", async () => {
    let resolveBackend: ((ids: number[]) => void) | undefined;
    const queryBoxSelection = vi.fn(
      () => new Promise<number[]>((resolve) => {
        resolveBackend = resolve;
      }),
    );
    const points = makeFixedPoints([{ id: 101, classNumber: 1 }]);
    const { wrapper } = await mountWithProviders(ScWaferMap, {
      props: {
        points,
        geometry: smallGeometry,
        waferRadiusNm: smallRadius,
        selectedIds: new Set(),
        queryBoxSelection,
        mode: "select",
      },
    });

    const canvas = wrapper.find(".swm-ol");
    await canvas.trigger("pointerdown", { button: 0, clientX: 300, clientY: 288 });
    await canvas.trigger("pointermove", { clientX: 312, clientY: 300 });
    const drag = canvas.trigger("pointerup", { clientX: 312, clientY: 300 });
    await nextTick();
    expect(wrapper.emitted("selection-change")?.at(-1)?.[0]).toContain(101);

    await canvas.trigger("dblclick");
    await nextTick();
    expect(wrapper.emitted("selection-change")?.at(-1)?.[0]).toEqual([]);

    resolveBackend?.([201, 202]);
    await drag;
    await nextTick();

    const lastEmit = wrapper.emitted("selection-change")?.at(-1)?.[0] as number[];
    expect(lastEmit).toEqual([]);
  });

  it("applies fresh backend results when started after clear", async () => {
    const points = makeFixedPoints([
      { id: 101, classNumber: 1 },
      { id: 102, classNumber: 1 },
    ]);
    const { wrapper } = await mountWithProviders(ScWaferMap, {
      props: {
        points,
        geometry: smallGeometry,
        waferRadiusNm: smallRadius,
        selectedIds: new Set(),
        queryBoxSelection: vi.fn().mockResolvedValue([201]),
        mode: "select",
      },
    });

    const canvas = wrapper.find(".swm-ol");
    await canvas.trigger("dblclick");
    await nextTick();
    expect(wrapper.emitted("selection-change")?.at(-1)?.[0]).toEqual([]);

    await canvas.trigger("pointerdown", { button: 0, clientX: 300, clientY: 288 });
    await canvas.trigger("pointermove", { clientX: 312, clientY: 300 });
    await canvas.trigger("pointerup", { clientX: 312, clientY: 300 });
    await nextTick();

    const lastEmit = wrapper.emitted("selection-change")?.at(-1)?.[0] as number[];
    expect(lastEmit).toEqual(expect.arrayContaining([201]));
  });

  it("discards first box-select results when second box-select supersedes", async () => {
    let resolveSlow: ((ids: number[]) => void) | undefined;
    let resolveFast: ((ids: number[]) => void) | undefined;
    let callCount = 0;
    const queryBoxSelection = vi.fn(
      () => new Promise<number[]>((resolve) => {
        callCount++;
        if (callCount === 1) {
          resolveSlow = resolve;
        } else {
          resolveFast = resolve;
        }
      }),
    );
    const points = makeFixedPoints([{ id: 101, classNumber: 1 }]);
    const { wrapper } = await mountWithProviders(ScWaferMap, {
      props: {
        points,
        geometry: smallGeometry,
        waferRadiusNm: smallRadius,
        selectedIds: new Set(),
        queryBoxSelection,
        mode: "select",
      },
    });

    const canvas = wrapper.find(".swm-ol");

    await canvas.trigger("pointerdown", { button: 0, clientX: 300, clientY: 288 });
    await canvas.trigger("pointermove", { clientX: 312, clientY: 300 });
    const dragA = canvas.trigger("pointerup", { clientX: 312, clientY: 300 });
    await nextTick();

    await canvas.trigger("pointerdown", { button: 0, clientX: 300, clientY: 288 });
    await canvas.trigger("pointermove", { clientX: 312, clientY: 300 });
    const dragB = canvas.trigger("pointerup", { clientX: 312, clientY: 300 });
    await nextTick();

    resolveFast?.([202]);
    await dragB;
    await nextTick();
    expect(wrapper.emitted("selection-change")?.at(-1)?.[0]).toEqual(
      expect.arrayContaining([202]),
    );

    const emitCountBefore = wrapper.emitted("selection-change")?.length ?? 0;
    resolveSlow?.([999]);
    await dragA;
    await nextTick();
    expect(wrapper.emitted("selection-change")?.length).toBe(emitCountBefore);
  });
});
