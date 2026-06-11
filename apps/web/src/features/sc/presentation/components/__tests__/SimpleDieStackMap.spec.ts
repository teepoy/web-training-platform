import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { nextTick } from "vue";
import { mountWithProviders } from "@/testing";
import SimpleDieStackMap from "../SimpleDieStackMap.vue";

vi.stubGlobal("ResizeObserver", class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
});

Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, value: 600 });
Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, value: 240 });

let mockCtx: any;
let strokeStyleSetter: any;

beforeEach(() => {
  strokeStyleSetter = vi.fn();
  mockCtx = {
    setTransform: vi.fn(),
    imageSmoothingEnabled: false,
    clearRect: vi.fn(),
    fillRect: vi.fn(),
    strokeRect: vi.fn(),
    fill: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    rect: vi.fn(),
    save: vi.fn(),
    restore: vi.fn(),
    clip: vi.fn(),
    drawImage: vi.fn(),
    _strokeStyle: "",
    get strokeStyle() { return this._strokeStyle; },
    set strokeStyle(v: any) { strokeStyleSetter(v); this._strokeStyle = v; },
    _fillStyle: "",
    get fillStyle() { return this._fillStyle; },
    set fillStyle(v: any) { this._fillStyle = v; },
    _lineWidth: 1,
    get lineWidth() { return this._lineWidth; },
    set lineWidth(v: any) { this._lineWidth = v; },
  };

  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation((type: string) => {
    if (type === "2d") return mockCtx as any;
    return null;
  });
});

function makePoints(count: number, options?: { hasImageFlag?: boolean; isSelected?: boolean }): {
  x: number; y: number; id: number; label: string; hasImageFlag: boolean; isSelectedFlag: boolean;
}[] {
  const points = [];
  for (let i = 0; i < count; i++) {
    points.push({
      x: i * 10,
      y: i * 10,
      id: i + 1,
      label: "1",
      hasImageFlag: options?.hasImageFlag ?? false,
      isSelectedFlag: options?.isSelected ?? false,
    });
  }
  return points;
}

describe("SimpleDieStackMap", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("die outline uses gray color (#9ca3af)", async () => {
    const points = makePoints(3);
    const { wrapper } = await mountWithProviders(SimpleDieStackMap, {
      props: {
        points,
        colorMap: { "1": "#ff0000" },
        dieSizeX: 500,
        dieSizeY: 500,
      },
    });
    await nextTick();
    await wrapper.setProps({ dieSizeX: 600 });
    await nextTick();

    expect(strokeStyleSetter).toHaveBeenCalledWith("#9ca3af");
  });

  it("does not draw outer canvas border", async () => {
    const points = makePoints(3);
    const { wrapper } = await mountWithProviders(SimpleDieStackMap, {
      props: {
        points,
        colorMap: { "1": "#ff0000" },
        dieSizeX: 500,
        dieSizeY: 500,
      },
    });
    await nextTick();
    await wrapper.setProps({ dieSizeX: 600 });
    await nextTick();

    const outerBorderCalls = mockCtx.strokeRect.mock.calls.filter(
      (call: any[]) => call[0] === 0.5 && call[1] === 0.5,
    );
    expect(outerBorderCalls.length).toBe(0);
  });

  it("image flag box retains black color", async () => {
    const points = makePoints(3, { hasImageFlag: true });
    const { wrapper } = await mountWithProviders(SimpleDieStackMap, {
      props: {
        points,
        colorMap: { "1": "#ff0000" },
        dieSizeX: 500,
        dieSizeY: 500,
      },
    });
    await nextTick();
    await wrapper.setProps({ dieSizeX: 600 });
    await nextTick();

    const blackStrokeCalls = mockCtx.strokeRect.mock.calls.filter(
      (call: any[]) => call[2] === 5,
    );
    expect(blackStrokeCalls.length).toBeGreaterThan(0);
  });
});
