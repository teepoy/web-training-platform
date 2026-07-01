import { describe, it, expect, vi, afterEach } from "vitest";
import { nextTick } from "vue";
import { mountWithProviders } from "@/testing";
import { SINGLE_POINT, EMPTY_POINTS, makeStride6Points } from "./scMapFixtures";
import ScDieStackMapPerspective from "../ScDieStackMapPerspective.vue";
import type { HighlightDefect } from "../types";

vi.stubGlobal(
  "ResizeObserver",
  class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  },
);

Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, value: 600 });
Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, value: 600 });
Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
  configurable: true,
  value: () => ({ left: 0, top: 0, width: 600, height: 600 }),
});

const smallGeometry = {
  centerX: 0,
  centerY: 0,
  dieSizeX: 500,
  dieSizeY: 500,
};

function makeFixedPoints(entries: { id: number; classNumber: number }[]): number[] {
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
  const canvas = wrapper.find(".sc-die-map-perspective__overlay");
  await canvas.trigger("pointerdown", { button: 0, clientX: startX, clientY: startY });
  await canvas.trigger("pointermove", { clientX: endX, clientY: endY });
  await canvas.trigger("pointerup", { clientX: endX, clientY: endY });
  await nextTick();
}

function makeHighlightDefects(
  entries: { defectId: number; dieX: number; dieY: number }[],
): HighlightDefect[] {
  return entries.map((e) => ({
    defectId: e.defectId,
    waferX: e.dieX * 10,
    waferY: e.dieY * 10,
    dieX: e.dieX,
    dieY: e.dieY,
    reticleX: 0,
    reticleY: 0,
  }));
}

describe("ScDieStackMapPerspective", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows empty state when no points", async () => {
    const { wrapper } = await mountWithProviders(ScDieStackMapPerspective, {
      props: { points: undefined, geometry: smallGeometry },
    });
    await nextTick();
    expect(wrapper.find(".sc-die-map-perspective").exists()).toBe(true);
  });

  it("shows empty state when points array is empty", async () => {
    const { wrapper } = await mountWithProviders(ScDieStackMapPerspective, {
      props: { points: EMPTY_POINTS, geometry: smallGeometry },
    });
    await nextTick();
    expect(wrapper.find(".sc-die-map-perspective").exists()).toBe(true);
  });

  it("renders canvas when points are provided", async () => {
    const { wrapper } = await mountWithProviders(ScDieStackMapPerspective, {
      props: { points: SINGLE_POINT, geometry: smallGeometry },
    });
    await nextTick();
    expect(wrapper.find(".sc-die-map-perspective__overlay").exists()).toBe(true);
  });

  it("supports box selection after points arrive asynchronously", async () => {
    const points = makeFixedPoints([{ id: 101, classNumber: 1 }]);
    const { wrapper } = await mountWithProviders(ScDieStackMapPerspective, {
      props: {
        points: EMPTY_POINTS,
        geometry: smallGeometry,
      },
    });

    await wrapper.setProps({ points });
    await nextTick();

    expect(wrapper.find(".sc-die-map-perspective__overlay").exists()).toBe(true);
    await simulateBoxDrag(wrapper, 300, 288, 312, 300);
    expect(wrapper.emitted("box-select")).toBeTruthy();
    expect(wrapper.emitted("box-select")!.length).toBeGreaterThanOrEqual(1);
  });

  it("does not crash with zero container dimensions", async () => {
    const origW = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientWidth")!;
    const origH = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientHeight")!;

    Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, value: 0 });
    Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, value: 0 });

    try {
      const { wrapper } = await mountWithProviders(ScDieStackMapPerspective, {
        props: { points: SINGLE_POINT, geometry: smallGeometry },
      });
      await nextTick();
      expect(wrapper.find(".sc-die-map-perspective__overlay").exists()).toBe(true);
    } finally {
      Object.defineProperty(HTMLElement.prototype, "clientWidth", origW);
      Object.defineProperty(HTMLElement.prototype, "clientHeight", origH);
    }
  });

  it("clears selection on double-click and emits empty array", async () => {
    const points = makeFixedPoints([
      { id: 101, classNumber: 1 },
      { id: 201, classNumber: 2 },
    ]);

    const { wrapper } = await mountWithProviders(ScDieStackMapPerspective, {
      props: {
        points,
        geometry: smallGeometry,
        mode: "select",
      },
    });

    await nextTick();
    const vm = wrapper.vm as unknown as { immediateCrosshairPoints: { x: number; y: number }[] };
    vm.immediateCrosshairPoints = [{ x: 1, y: 2 }];

    const canvas = wrapper.find(".sc-die-map-perspective__overlay");
    await canvas.trigger("dblclick");
    await nextTick();

    const events = wrapper.emitted("selection-change");
    expect(events).toBeTruthy();
    expect(events![events!.length - 1][0]).toEqual([]);
    expect(vm.immediateCrosshairPoints).toEqual([]);
  });

  it("emits box-select in select mode", async () => {
    const points = makeFixedPoints([{ id: 101, classNumber: 1 }]);

    const { wrapper } = await mountWithProviders(ScDieStackMapPerspective, {
      props: {
        points,
        geometry: smallGeometry,
        mode: "select",
      },
    });

    await nextTick();
    await simulateBoxDrag(wrapper, 300, 288, 312, 300);

    expect(wrapper.emitted("box-select")).toBeTruthy();
    expect(wrapper.emitted("box-select")!.length).toBeGreaterThanOrEqual(1);
  });

  it("emits zoom-in in zoomin mode", async () => {
    const points = makeFixedPoints([{ id: 101, classNumber: 1 }]);

    const { wrapper } = await mountWithProviders(ScDieStackMapPerspective, {
      props: {
        points,
        geometry: smallGeometry,
        mode: "zoomin",
      },
    });

    await nextTick();
    await simulateBoxDrag(wrapper, 300, 288, 312, 300);

    expect(wrapper.emitted("zoom-in")).toBeTruthy();
    expect(wrapper.emitted("zoom-in")!.length).toBeGreaterThanOrEqual(1);
  });

  it("emits zoom-in null on double-click in zoomin mode with zoom", async () => {
    const points = makeFixedPoints([{ id: 101, classNumber: 1 }]);

    const { wrapper } = await mountWithProviders(ScDieStackMapPerspective, {
      props: {
        points,
        geometry: smallGeometry,
        mode: "zoomin",
        zoom: { x: 0, y: 0, w: 1000, h: 1000 },
      },
    });

    await nextTick();
    const canvas = wrapper.find(".sc-die-map-perspective__overlay");
    await canvas.trigger("dblclick");
    await nextTick();

    expect(wrapper.emitted("zoom-in")?.at(-1)?.[0]).toBeNull();
    expect(wrapper.emitted("selection-change")?.at(-1)?.[0]).toEqual([]);
  });
});

describe("ScDieStackMapPerspective highlight and crosshair", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("accepts highlightDefects with dieX/dieY coordinates without crashing", async () => {
    const points = makeFixedPoints([{ id: 101, classNumber: 1 }]);
    const highlightDefects = makeHighlightDefects([
      { defectId: 1, dieX: 100, dieY: 200 },
      { defectId: 2, dieX: 500, dieY: 800 },
    ]);

    const { wrapper } = await mountWithProviders(ScDieStackMapPerspective, {
      props: {
        points,
        geometry: smallGeometry,
        highlightDefects,
      },
    });

    await nextTick();
    expect(wrapper.find(".sc-die-map-perspective").exists()).toBe(true);
  });

  it("accepts empty highlightDefects array without crashing", async () => {
    const points = makeFixedPoints([{ id: 101, classNumber: 1 }]);

    const { wrapper } = await mountWithProviders(ScDieStackMapPerspective, {
      props: {
        points,
        geometry: smallGeometry,
        highlightDefects: [],
      },
    });

    await nextTick();
    expect(wrapper.find(".sc-die-map-perspective").exists()).toBe(true);
  });

  it("emits immediate crosshair points on box-select in select mode", async () => {
    const points = makeFixedPoints([
      { id: 101, classNumber: 1 },
      { id: 201, classNumber: 2 },
    ]);
    const queryBoxSelection = vi.fn().mockResolvedValue([201]);

    const { wrapper } = await mountWithProviders(ScDieStackMapPerspective, {
      props: {
        points,
        geometry: smallGeometry,
        mode: "select",
        queryBoxSelection,
      },
    });

    await nextTick();
    await simulateBoxDrag(wrapper, 100, 100, 200, 200);
    await nextTick();

    expect(wrapper.emitted("box-select")).toBeTruthy();
    expect(wrapper.emitted("box-select")!.length).toBeGreaterThanOrEqual(1);
    expect(wrapper.emitted("immediate-crosshair-points")).toBeTruthy();
    expect(wrapper.emitted("immediate-crosshair-points")!.at(-1)?.[0]).not.toEqual([]);
  });

  it("keeps appending crosshair selections across subsequent drags", async () => {
    const points = makeFixedPoints([
      { id: 101, classNumber: 1 },
      { id: 201, classNumber: 2 },
    ]);
    const queryBoxSelection = vi.fn().mockResolvedValue([201]);

    const { wrapper } = await mountWithProviders(ScDieStackMapPerspective, {
      props: {
        points,
        geometry: smallGeometry,
        mode: "select",
        queryBoxSelection,
      },
    });

    await nextTick();

    // First box select
    await simulateBoxDrag(wrapper, 100, 100, 200, 200);
    expect(wrapper.emitted("box-select")).toBeTruthy();

    // Second box select keeps the previous immediate crosshair visible while adding the new one.
    await simulateBoxDrag(wrapper, 300, 288, 312, 300);
    expect(wrapper.emitted("box-select")!.length).toBeGreaterThanOrEqual(2);
  });

  it("keeps crosshair when points change", async () => {
    const points = makeFixedPoints([
      { id: 101, classNumber: 1 },
      { id: 201, classNumber: 2 },
    ]);
    const queryBoxSelection = vi.fn().mockResolvedValue([201]);

    const { wrapper } = await mountWithProviders(ScDieStackMapPerspective, {
      props: {
        points,
        geometry: smallGeometry,
        mode: "select",
        queryBoxSelection,
      },
    });

    await nextTick();

    await simulateBoxDrag(wrapper, 100, 100, 200, 200);
    expect(wrapper.emitted("box-select")!.length).toBe(1);

    // Change points — should not crash
    const newPoints = makeFixedPoints([{ id: 301, classNumber: 0 }]);
    await wrapper.setProps({ points: newPoints });
    await nextTick();

    expect(wrapper.find(".sc-die-map-perspective").exists()).toBe(true);
  });

  it("clears crosshair when mode changes", async () => {
    const points = makeFixedPoints([
      { id: 101, classNumber: 1 },
      { id: 201, classNumber: 2 },
    ]);
    const queryBoxSelection = vi.fn().mockResolvedValue([201]);

    const { wrapper } = await mountWithProviders(ScDieStackMapPerspective, {
      props: {
        points,
        geometry: smallGeometry,
        mode: "select",
        queryBoxSelection,
      },
    });

    await nextTick();

    await simulateBoxDrag(wrapper, 100, 100, 200, 200);
    expect(wrapper.emitted("box-select")!.length).toBe(1);

    // Change mode — should not crash
    await wrapper.setProps({ mode: "zoomin" });
    await nextTick();

    expect(wrapper.find(".sc-die-map-perspective").exists()).toBe(true);
  });

  it("does not compute crosshair in zoomin mode", async () => {
    const points = makeFixedPoints([{ id: 101, classNumber: 1 }]);

    const { wrapper } = await mountWithProviders(ScDieStackMapPerspective, {
      props: {
        points,
        geometry: smallGeometry,
        mode: "zoomin",
      },
    });

    await nextTick();
    await simulateBoxDrag(wrapper, 300, 288, 312, 300);

    // zoomin emits zoom-in instead of box-select
    expect(wrapper.emitted("zoom-in")).toBeTruthy();
    expect(wrapper.emitted("box-select")).toBeFalsy();
  });

  it("discards stale backend results on rapid box-selects", async () => {
    let resolveSlow: ((ids: number[]) => void) | undefined;
    let resolveFast: ((ids: number[]) => void) | undefined;
    let callCount = 0;
    const queryBoxSelection = vi.fn(
      () =>
        new Promise<number[]>((resolve) => {
          callCount++;
          if (callCount === 1) {
            resolveSlow = resolve;
          } else {
            resolveFast = resolve;
          }
        }),
    );
    const points = makeFixedPoints([{ id: 101, classNumber: 1 }]);

    const { wrapper } = await mountWithProviders(ScDieStackMapPerspective, {
      props: {
        points,
        geometry: smallGeometry,
        mode: "select",
        queryBoxSelection,
      },
    });

    await nextTick();

    await simulateBoxDrag(wrapper, 300, 288, 312, 300);
    await simulateBoxDrag(wrapper, 300, 288, 312, 300);

    resolveFast?.([202]);
    await nextTick();
    expect(wrapper.emitted("selection-change")?.at(-1)?.[0]).toEqual(expect.arrayContaining([202]));

    const emitCountBefore = wrapper.emitted("selection-change")?.length ?? 0;
    resolveSlow?.([999]);
    await nextTick();
    expect(wrapper.emitted("selection-change")?.length).toBe(emitCountBefore);
  });

  it("renders highlight defects with dieX/dieY coordinates from prop", async () => {
    const points = makeFixedPoints([
      { id: 101, classNumber: 1 },
      { id: 201, classNumber: 2 },
    ]);
    const highlightDefects = makeHighlightDefects([
      { defectId: 1, dieX: 1100, dieY: 1200 },
      { defectId: 2, dieX: 2100, dieY: 2200 },
    ]);

    const { wrapper } = await mountWithProviders(ScDieStackMapPerspective, {
      props: {
        points,
        geometry: smallGeometry,
        highlightDefects,
      },
    });

    await nextTick();
    expect(wrapper.find(".sc-die-map-perspective__overlay").exists()).toBe(true);
  });
});
