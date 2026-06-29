import { defineComponent } from "vue";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { nextTick } from "vue";
import { mountWithProviders } from "@/testing";
import ScWaferMapPerspective from "../ScWaferMapPerspective.vue";

vi.mock("../SimplePerspectiveMap.vue", () => ({
  default: defineComponent({
    name: "SimplePerspectiveMap",
    props: {
      points: Array,
      colorMap: Object,
      zoom: Object,
      centerX: Number,
      centerY: Number,
      dataRangeNm: Number,
    },
    template: "<div />",
  }),
}));

vi.mock("../scMapViewport", async () => {
  const actual = await vi.importActual<typeof import("../scMapViewport")>("../scMapViewport");
  return {
    ...actual,
    dataToScreen: vi.fn((_t: unknown, x: number, y: number) => [x, y]),
    screenToData: vi.fn((_t: unknown, sx: number, sy: number) => [sx, sy]),
  };
});

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

interface CtxSpy {
  setTransform: ReturnType<typeof vi.fn>;
  clearRect: ReturnType<typeof vi.fn>;
  fillRect: ReturnType<typeof vi.fn>;
  strokeRect: ReturnType<typeof vi.fn>;
  beginPath: ReturnType<typeof vi.fn>;
  moveTo: ReturnType<typeof vi.fn>;
  lineTo: ReturnType<typeof vi.fn>;
  stroke: ReturnType<typeof vi.fn>;
  fillStyle: string;
  strokeStyle: string;
  lineWidth: number;
}

function createCtxSpy(): CtxSpy {
  return {
    setTransform: vi.fn(),
    clearRect: vi.fn(),
    fillRect: vi.fn(),
    strokeRect: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    fillStyle: "#000000",
    strokeStyle: "#000000",
    lineWidth: 0,
  };
}

/** Return the global invocation order of each spy method call. */
function spyCallOrder(spy: CtxSpy): Record<string, number[]> {
  const methods = [
    "setTransform",
    "clearRect",
    "fillRect",
    "strokeRect",
    "beginPath",
    "moveTo",
    "lineTo",
    "stroke",
  ] as const;
  const entries: [string, number][] = [];
  for (const m of methods) {
    const mocked = spy[m] as ReturnType<typeof vi.fn>;
    for (const call of mocked.mock.invocationCallOrder ?? []) {
      entries.push([m, call]);
    }
  }
  entries.sort((a, b) => a[1] - b[1]);
  const result: Record<string, number[]> = {};
  for (const [name, globalIdx] of entries) {
    if (!result[name]) result[name] = [];
    result[name]!.push(globalIdx);
  }
  return result;
}

const geometry = {
  centerX: 0,
  centerY: 0,
  originX: 0,
  originY: 0,
  dieSizeX: 500,
  dieSizeY: 500,
};

function makePoints(entries: { x: number; y: number }[]): number[] {
  const result: number[] = [];
  for (const e of entries) {
    result.push(e.x, e.y, 0, 0, 0, 0);
  }
  return result;
}

async function simulateDrag(
  wrapper: ReturnType<typeof mountWithProviders>["wrapper"],
  startX: number,
  startY: number,
  endX: number,
  endY: number,
) {
  const canvas = wrapper.find(".sc-wafer-map-perspective__overlay");
  await canvas.trigger("pointerdown", { button: 0, clientX: startX, clientY: startY });
  await canvas.trigger("pointermove", { clientX: endX, clientY: endY });
  await canvas.trigger("pointerup", { clientX: endX, clientY: endY });
  await nextTick();
}

/** Spy on the mocked prepareOverlayCanvas to control the overlay canvas context. */
import * as scMapViewport from "../scMapViewport";

describe("ScWaferMapPerspective", () => {
  let ctxSpy: CtxSpy;

  beforeEach(() => {
    ctxSpy = createCtxSpy();
    vi.spyOn(scMapViewport, "prepareOverlayCanvas").mockImplementation(
      (cvs: HTMLCanvasElement, _size: unknown) => {
        if (cvs.classList.contains("sc-wafer-map-perspective__overlay")) {
          return ctxSpy as unknown as CanvasRenderingContext2D;
        }
        return null;
      },
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("draws highlight defects as purple 3x3 dots at correct screen positions", async () => {
    const highlightDefects = [
      { defectId: 1, waferX: 100, waferY: 200, dieX: 0, dieY: 0, reticleX: 0, reticleY: 0 },
    ];

    const { wrapper } = await mountWithProviders(ScWaferMapPerspective, {
      props: {
        points: makePoints([]),
        geometry,
        highlightDefects,
        mode: "select" as const,
      },
    });

    const canvas = wrapper.find(".sc-wafer-map-perspective__overlay");
    await canvas.trigger("pointerdown", { button: 0, clientX: 10, clientY: 10 });
    await nextTick();

    expect(ctxSpy.fillStyle).toBe("#A855F7");
    expect(ctxSpy.fillRect).toHaveBeenCalledWith(100 - 1.5, 200 - 1.5, 3, 3);
  });

  it("computes and draws crosshairs for points inside the drag region", async () => {
    const points = makePoints([{ x: 100, y: 200 }]);

    const { wrapper } = await mountWithProviders(ScWaferMapPerspective, {
      props: {
        points,
        geometry,
        mode: "select" as const,
        queryBoxSelection: vi.fn().mockResolvedValue([]),
      },
    });

    await nextTick();
    await simulateDrag(wrapper, 90, 190, 110, 210);

    expect(ctxSpy.stroke).toHaveBeenCalled();
    expect(ctxSpy.beginPath).toHaveBeenCalled();
    expect(ctxSpy.moveTo).toHaveBeenCalledWith(97, 200);
    expect(ctxSpy.lineTo).toHaveBeenCalledWith(103, 200);
    expect(ctxSpy.strokeStyle).toBe("#000000");
  });

  it("clears crosshairs when binned points prop updates", async () => {
    const points = makePoints([{ x: 100, y: 200 }]);

    const { wrapper } = await mountWithProviders(ScWaferMapPerspective, {
      props: {
        points,
        geometry,
        mode: "select" as const,
        queryBoxSelection: vi.fn().mockResolvedValue([]),
      },
    });

    await nextTick();
    await simulateDrag(wrapper, 90, 190, 110, 210);
    expect(ctxSpy.stroke).toHaveBeenCalled();

    vi.clearAllMocks();

    const newPoints = makePoints([{ x: 300, y: 400 }]);
    await wrapper.setProps({ points: newPoints });
    await nextTick();

    expect(ctxSpy.stroke).not.toHaveBeenCalled();
    expect(ctxSpy.beginPath).not.toHaveBeenCalled();
  });

  it("does not compute crosshairs in zoom mode", async () => {
    const points = makePoints([{ x: 100, y: 200 }]);

    const { wrapper } = await mountWithProviders(ScWaferMapPerspective, {
      props: {
        points,
        geometry,
        mode: "zoomin" as const,
      },
    });

    await nextTick();
    await simulateDrag(wrapper, 90, 190, 110, 210);

    expect(ctxSpy.beginPath).not.toHaveBeenCalled();
    expect(ctxSpy.stroke).not.toHaveBeenCalled();
  });

  it("draws highlights before crosshairs in overlay order", async () => {
    const points = makePoints([{ x: 100, y: 200 }]);
    const highlightDefects = [
      { defectId: 1, waferX: 50, waferY: 60, dieX: 0, dieY: 0, reticleX: 0, reticleY: 0 },
    ];

    const { wrapper } = await mountWithProviders(ScWaferMapPerspective, {
      props: {
        points,
        geometry,
        mode: "select" as const,
        highlightDefects,
        queryBoxSelection: vi.fn().mockResolvedValue([]),
      },
    });

    await nextTick();
    await simulateDrag(wrapper, 90, 190, 110, 210);

    const order = spyCallOrder(ctxSpy);
    const highlightFillIdx = order["fillRect"]?.[0] ?? Infinity;
    const crosshairBeginIdx = order["beginPath"]?.[0] ?? Infinity;

    expect(highlightFillIdx).toBeLessThan(crosshairBeginIdx);
  });

  it("draws no highlight dots when highlightDefects is empty", async () => {
    const { wrapper } = await mountWithProviders(ScWaferMapPerspective, {
      props: {
        points: makePoints([]),
        geometry,
        highlightDefects: [],
        mode: "select" as const,
      },
    });

    const canvas = wrapper.find(".sc-wafer-map-perspective__overlay");
    await canvas.trigger("pointerdown", { button: 0, clientX: 10, clientY: 10 });
    await nextTick();

    expect(ctxSpy.fillRect).not.toHaveBeenCalled();
  });
});
