import { afterEach, describe, expect, it, vi } from "vitest";
import {
  clampRegionToBounds,
  defineScMapElement,
  normalizeWheelDelta,
  SC_MAP_WHEEL_ZOOM_COMMIT_DELAY_MS,
  type ScMapElement,
  type ScMapRegion,
  zoomRegionAroundPoint,
} from "@platform/sc-map-element";

describe("sc-map viewport interactions", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("normalizes pixel, line, and page wheel deltas", () => {
    expect(normalizeWheelDelta(4, 0, 600)).toBe(4);
    expect(normalizeWheelDelta(4, 1, 600)).toBe(64);
    expect(normalizeWheelDelta(2, 2, 600)).toBe(1200);
  });

  it("keeps the anchor fixed while zooming and clamps the viewport to map bounds", () => {
    const bounds = { x: 0, y: 0, w: 100, h: 100 };
    const zoomed = zoomRegionAroundPoint(bounds, bounds, { x: 75, y: 25 }, 0.5);

    expect(zoomed).toEqual({ x: 37.5, y: 12.5, w: 50, h: 50 });
    expect((75 - zoomed.x) / zoomed.w).toBeCloseTo(0.75);
    expect((25 - zoomed.y) / zoomed.h).toBeCloseTo(0.25);
    expect(clampRegionToBounds({ x: -20, y: 80, w: 40, h: 40 }, bounds)).toEqual({
      x: 0,
      y: 60,
      w: 40,
      h: 40,
    });
  });

  it("coalesces wheel input into one frame and commits once after the trailing delay", () => {
    vi.useFakeTimers();
    let frameCallback: FrameRequestCallback | null = null;
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      frameCallback = callback;
      return 1;
    });
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => undefined);
    const element = createMapElement();
    const overlay = element.shadowRoot?.querySelector<HTMLCanvasElement>(".overlay");
    const committed: Array<ScMapRegion | null> = [];
    element.addEventListener("zoom-in", (event) => {
      committed.push((event as CustomEvent<ScMapRegion | null>).detail);
    });

    const first = wheelEvent(-50, 75, 50);
    const second = wheelEvent(-50, 75, 50);
    overlay?.dispatchEvent(first);
    overlay?.dispatchEvent(second);

    expect(first.defaultPrevented).toBe(true);
    expect(second.defaultPrevented).toBe(true);
    expect(window.requestAnimationFrame).toHaveBeenCalledTimes(1);
    expect(committed).toEqual([]);

    frameCallback?.(0);
    vi.advanceTimersByTime(SC_MAP_WHEEL_ZOOM_COMMIT_DELAY_MS - 1);
    expect(committed).toEqual([]);
    vi.advanceTimersByTime(1);

    expect(committed).toHaveLength(1);
    const region = committed[0];
    expect(region).not.toBeNull();
    if (!region) return;
    expect(region.w).toBeCloseTo(300_000_000 * Math.exp(-0.15));
    expect((75_000_000 - region.x) / region.w).toBeCloseTo(0.75);
  });

  it("uses ordinary two-finger wheel deltas to pan", () => {
    vi.useFakeTimers();
    let frameCallback: FrameRequestCallback | null = null;
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      frameCallback = callback;
      return 1;
    });
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => undefined);
    const element = createMapElement();
    element.zoom = { x: -75_000_000, y: -75_000_000, w: 150_000_000, h: 150_000_000 };
    const overlay = element.shadowRoot?.querySelector<HTMLCanvasElement>(".overlay");
    const committed: Array<ScMapRegion | null> = [];
    element.addEventListener("zoom-in", (event) => {
      committed.push((event as CustomEvent<ScMapRegion | null>).detail);
    });

    overlay?.dispatchEvent(
      wheelEvent(20, 50, 50, {
        ctrlKey: false,
        deltaX: 10,
      }),
    );
    frameCallback?.(0);
    vi.advanceTimersByTime(SC_MAP_WHEEL_ZOOM_COMMIT_DELAY_MS);

    expect(committed).toHaveLength(1);
    expect(committed[0]).toEqual({
      x: -60_000_000,
      y: -105_000_000,
      w: 150_000_000,
      h: 150_000_000,
    });
  });

  it("uses right drag for pan without changing the active left-drag tool", () => {
    const context = overlayContextStub();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
      context as unknown as CanvasRenderingContext2D,
    );
    const element = createMapElement();
    element.zoom = { x: -75_000_000, y: -75_000_000, w: 150_000_000, h: 150_000_000 };
    const overlay = element.shadowRoot?.querySelector<HTMLCanvasElement>(".overlay");
    const zoomEvents: Array<ScMapRegion | null> = [];
    let boxSelections = 0;
    element.addEventListener("zoom-in", (event) => {
      zoomEvents.push((event as CustomEvent<ScMapRegion | null>).detail);
    });
    element.addEventListener("box-select", () => {
      boxSelections += 1;
    });

    overlay?.dispatchEvent(pointerEvent("pointerdown", 2, 50, 50));
    overlay?.dispatchEvent(pointerEvent("pointermove", -1, 40, 50));
    overlay?.dispatchEvent(pointerEvent("pointerup", 2, 40, 50));

    expect(zoomEvents).toHaveLength(1);
    expect(zoomEvents[0]?.x).toBeCloseTo(-60_000_000);
    expect(boxSelections).toBe(0);

    overlay?.dispatchEvent(pointerEvent("pointerdown", 0, 20, 20));
    overlay?.dispatchEvent(pointerEvent("pointermove", -1, 40, 40));
    overlay?.dispatchEvent(pointerEvent("pointerup", 0, 40, 40));
    expect(boxSelections).toBe(1);
  });

  it("cancels an uncommitted wheel viewport when the map mode changes", () => {
    vi.useFakeTimers();
    let frameCallback: FrameRequestCallback | null = null;
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      frameCallback = callback;
      return 1;
    });
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => undefined);
    const element = createMapElement();
    const overlay = element.shadowRoot?.querySelector<HTMLCanvasElement>(".overlay");
    const committed: Array<ScMapRegion | null> = [];
    element.addEventListener("zoom-in", (event) => {
      committed.push((event as CustomEvent<ScMapRegion | null>).detail);
    });

    overlay?.dispatchEvent(wheelEvent(-100, 50, 50));
    frameCallback?.(0);
    element.mode = "die";
    vi.advanceTimersByTime(SC_MAP_WHEEL_ZOOM_COMMIT_DELAY_MS);

    expect(committed).toEqual([]);
  });

  it("cancels a right-drag preview without committing on pointer cancel", () => {
    const context = overlayContextStub();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
      context as unknown as CanvasRenderingContext2D,
    );
    const element = createMapElement();
    element.zoom = { x: -75_000_000, y: -75_000_000, w: 150_000_000, h: 150_000_000 };
    const overlay = element.shadowRoot?.querySelector<HTMLCanvasElement>(".overlay");
    let commits = 0;
    element.addEventListener("zoom-in", () => {
      commits += 1;
    });

    overlay?.dispatchEvent(pointerEvent("pointerdown", 2, 50, 50));
    overlay?.dispatchEvent(pointerEvent("pointermove", -1, 40, 50));
    overlay?.dispatchEvent(pointerEvent("pointercancel", 2, 40, 50));

    expect(commits).toBe(0);
  });
});

function createMapElement(): ScMapElement {
  defineScMapElement();
  const element = document.createElement("sc-map") as ScMapElement;
  Object.defineProperties(element, {
    clientWidth: { configurable: true, value: 100 },
    clientHeight: { configurable: true, value: 100 },
  });
  vi.spyOn(element, "getBoundingClientRect").mockReturnValue({
    x: 0,
    y: 0,
    top: 0,
    right: 100,
    bottom: 100,
    left: 0,
    width: 100,
    height: 100,
    toJSON: () => ({}),
  });
  return element;
}

function wheelEvent(
  deltaY: number,
  clientX: number,
  clientY: number,
  options: { ctrlKey?: boolean; deltaX?: number } = {},
): WheelEvent {
  const deltaX = options.deltaX ?? 0;
  const ctrlKey = options.ctrlKey ?? true;
  const event = new WheelEvent("wheel", {
    bubbles: true,
    cancelable: true,
    clientX,
    clientY,
    ctrlKey,
    deltaX,
    deltaY,
    deltaMode: 0,
  });
  Object.defineProperties(event, {
    clientX: { configurable: true, value: clientX },
    clientY: { configurable: true, value: clientY },
    ctrlKey: { configurable: true, value: ctrlKey },
    deltaX: { configurable: true, value: deltaX },
  });
  return event;
}

function pointerEvent(
  type: "pointerdown" | "pointermove" | "pointerup" | "pointercancel",
  button: number,
  clientX: number,
  clientY: number,
): PointerEvent {
  return new PointerEvent(type, { bubbles: true, cancelable: true, button, clientX, clientY });
}

function overlayContextStub(): Partial<CanvasRenderingContext2D> {
  return {
    setTransform: vi.fn(),
    clearRect: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    closePath: vi.fn(),
    fill: vi.fn(),
    stroke: vi.fn(),
    fillRect: vi.fn(),
    strokeRect: vi.fn(),
  };
}
