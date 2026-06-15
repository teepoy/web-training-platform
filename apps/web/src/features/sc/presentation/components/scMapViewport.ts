export interface ScMapBounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

export interface ScMapSize {
  width: number;
  height: number;
}

export interface ScMapTransform extends ScMapSize {
  cx: number;
  cy: number;
  scale: number;
  offsetX: number;
  offsetY: number;
}

export interface ScMapRegion {
  x: number;
  y: number;
  w: number;
  h: number;
}

export function measureMapElement(element: HTMLElement | null): ScMapSize | null {
  if (!element) return null;
  const rect = element.getBoundingClientRect();
  const width = Math.round(rect.width || element.clientWidth);
  const height = Math.round(rect.height || element.clientHeight);
  if (width <= 0 || height <= 0) return null;
  return { width, height };
}

export function normalizeBounds(bounds: ScMapBounds): ScMapBounds {
  let { minX, maxX, minY, maxY } = bounds;
  if (minX === maxX) {
    minX -= 0.5;
    maxX += 0.5;
  }
  if (minY === maxY) {
    minY -= 0.5;
    maxY += 0.5;
  }
  return { minX, maxX, minY, maxY };
}

export function boundsFromRegion(region: ScMapRegion): ScMapBounds {
  return normalizeBounds({
    minX: region.x,
    maxX: region.x + region.w,
    minY: region.y,
    maxY: region.y + region.h,
  });
}

export function buildMapTransform(
  size: ScMapSize,
  bounds: ScMapBounds,
  paddingRatio = 0.9,
): ScMapTransform {
  const normalized = normalizeBounds(bounds);
  const spanX = normalized.maxX - normalized.minX;
  const spanY = normalized.maxY - normalized.minY;
  const scale = Math.min((size.width * paddingRatio) / spanX, (size.height * paddingRatio) / spanY);
  return {
    width: size.width,
    height: size.height,
    cx: size.width / 2,
    cy: size.height / 2,
    scale: Number.isFinite(scale) && scale > 0 ? scale : 1,
    offsetX: -(normalized.minX + normalized.maxX) / 2,
    offsetY: -(normalized.minY + normalized.maxY) / 2,
  };
}

export function screenToData(transform: ScMapTransform, sx: number, sy: number): [number, number] {
  return [
    (sx - transform.cx) / transform.scale - transform.offsetX,
    (transform.cy - sy) / transform.scale - transform.offsetY,
  ];
}

export function dataToScreen(transform: ScMapTransform, x: number, y: number): [number, number] {
  return [
    transform.cx + (x + transform.offsetX) * transform.scale,
    transform.cy - (y + transform.offsetY) * transform.scale,
  ];
}

export function eventToLocalPoint(
  element: HTMLElement | null,
  event: MouseEvent,
): [number, number] {
  const rect = element?.getBoundingClientRect();
  if (!rect) return [0, 0];
  return [event.clientX - rect.left, event.clientY - rect.top];
}

export function constrainDragToAspect(
  start: { x: number; y: number },
  current: { x: number; y: number },
  size: ScMapSize,
): { x: number; y: number } {
  const rawW = Math.abs(current.x - start.x);
  const rawH = Math.abs(current.y - start.y);
  if (rawW <= 0 || rawH <= 0 || size.width <= 0 || size.height <= 0) return current;

  const aspect = size.width / size.height;
  const rawAspect = rawW / rawH;
  if (rawAspect > aspect) {
    const height = rawW / aspect;
    const sign = Math.sign(current.y - start.y) || 1;
    return { x: current.x, y: start.y + sign * height };
  }
  if (rawAspect < aspect) {
    const width = rawH * aspect;
    const sign = Math.sign(current.x - start.x) || 1;
    return { x: start.x + sign * width, y: current.y };
  }
  return current;
}

export function prepareOverlayCanvas(
  canvas: HTMLCanvasElement,
  size: ScMapSize,
): CanvasRenderingContext2D | null {
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  const dpr = typeof window === "undefined" ? 1 : window.devicePixelRatio || 1;
  const pixelWidth = Math.max(1, Math.round(size.width * dpr));
  const pixelHeight = Math.max(1, Math.round(size.height * dpr));
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
    canvas.width = pixelWidth;
    canvas.height = pixelHeight;
  }
  canvas.style.width = `${size.width}px`;
  canvas.style.height = `${size.height}px`;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, size.width, size.height);
  return ctx;
}
