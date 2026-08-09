import type { ScMapBounds, ScMapRegion } from "./types";
import {
  createMapArrowDataset,
  type MapArrowDataset,
  type MapProjectionSpec,
  type MapSelectionCommand,
} from "./map-arrow-client";
import ScMapRenderWorker from "./sc-map-render.worker?worker&inline";
import { encodeLegendColorMap } from "./legend-key-codec";
import { fitMapRegionToViewport, type ScMapRenderViewport } from "./map-projection";

export const SC_MAP_TAG_NAME = "sc-map";
export type ScMapMode = "wafer" | "die" | "reticle";
export type ScMapInteractionMode = "select" | "lasso" | "zoomin" | "pan";

export interface ScMapPoint {
  x: number;
  y: number;
}

export interface ScMapLassoSelection {
  points: ScMapPoint[];
  region: ScMapRegion;
}

export interface ScMapGeometry {
  waferRadiusNm: number;
  centerX: number;
  centerY: number;
  originX: number;
  originY: number;
  dieSizeX: number;
  dieSizeY: number;
  reticleXDieCount: number;
  reticleYDieCount: number;
}

interface ScMapHighlight {
  waferX: number;
  waferY: number;
  dieX: number;
  dieY: number;
  reticleX: number;
  reticleY: number;
}

export interface ScMapProgress {
  progress: number;
  stage: string;
}

export interface ScMapErrorDetail {
  context: string;
  message: string;
  stack?: string;
}

export const SC_MAP_WHEEL_ZOOM_SENSITIVITY = 0.0015;
export const SC_MAP_WHEEL_ZOOM_COMMIT_DELAY_MS = 120;

const MIN_VIEWPORT_RATIO = 1 / 10_000;
const MIN_WHEEL_FRAME_FACTOR = 0.8;
const MAX_WHEEL_FRAME_FACTOR = 1.25;
const WHEEL_LINE_HEIGHT_PX = 16;

export function normalizeWheelDelta(deltaY: number, deltaMode: number, pageHeight: number): number {
  if (deltaMode === 1) return deltaY * WHEEL_LINE_HEIGHT_PX;
  if (deltaMode === 2) return deltaY * Math.max(1, pageHeight);
  return deltaY;
}

export function clampRegionToBounds(region: ScMapRegion, bounds: ScMapRegion): ScMapRegion {
  const width = Math.min(bounds.w, region.w);
  const height = Math.min(bounds.h, region.h);
  return {
    x: Math.min(bounds.x + bounds.w - width, Math.max(bounds.x, region.x)),
    y: Math.min(bounds.y + bounds.h - height, Math.max(bounds.y, region.y)),
    w: width,
    h: height,
  };
}

export function zoomRegionAroundPoint(
  region: ScMapRegion,
  bounds: ScMapRegion,
  anchor: ScMapPoint,
  factor: number,
): ScMapRegion {
  if (!Number.isFinite(factor) || factor <= 0) {
    throw new Error(`Invalid zoom factor: ${factor}`);
  }
  const width = Math.min(bounds.w, Math.max(bounds.w * MIN_VIEWPORT_RATIO, region.w * factor));
  const height = Math.min(bounds.h, Math.max(bounds.h * MIN_VIEWPORT_RATIO, region.h * factor));
  const anchorRatioX = (anchor.x - region.x) / region.w;
  const anchorRatioY = (anchor.y - region.y) / region.h;
  return clampRegionToBounds(
    {
      x: anchor.x - anchorRatioX * width,
      y: anchor.y - anchorRatioY * height,
      w: width,
      h: height,
    },
    bounds,
  );
}

function sameRegion(left: ScMapRegion | null, right: ScMapRegion | null): boolean {
  if (left === null || right === null) return left === right;
  return left.x === right.x && left.y === right.y && left.w === right.w && left.h === right.h;
}

interface Transform {
  scale: number;
  centerX: number;
  centerY: number;
  offsetX: number;
  offsetY: number;
}

const DEFAULT_GEOMETRY: ScMapGeometry = {
  waferRadiusNm: 150_000_000,
  centerX: 0,
  centerY: 0,
  originX: 0,
  originY: 0,
  dieSizeX: 100_000,
  dieSizeY: 100_000,
  reticleXDieCount: 2,
  reticleYDieCount: 6,
};

export class ScMapElement extends HTMLElement {
  readonly #background: HTMLCanvasElement;
  readonly #pointsCanvas: HTMLCanvasElement;
  readonly #overlay: HTMLCanvasElement;
  #pointsContext: ImageBitmapRenderingContext | null = null;
  #worker: Worker | null = null;
  #arrowDataset: MapArrowDataset | null = null;
  #arrowData: ArrayBuffer | readonly ArrayBuffer[] | null = null;
  #arrowLegendColumn = "class_number";
  #hiddenLegendKeys: string[] = [];
  #datasetRevision = 0;
  #datasetLoadScheduled = false;
  #projectionRevision = 0;
  #projectionRunning = false;
  #resizeObserver: ResizeObserver | null = null;
  #frame: number | null = null;
  #points = new Float32Array();
  #legendKeys: string[] = [];
  #colorMap: Record<string, string> = {};
  #showImageMarkers = true;
  #defectSize = 2;
  #mode: ScMapMode = "wafer";
  #interactionMode: ScMapInteractionMode = "select";
  #zoom: ScMapRegion | null = null;
  #dataBounds: ScMapBounds | null = null;
  #geometry: ScMapGeometry = { ...DEFAULT_GEOMETRY };
  #highlights: ScMapHighlight[] = [];
  #highlightDefectIds: number[] = [];
  #highlightResolutionRevision = 0;
  #highlightResolutionScheduled = false;
  #selectionIds: number[] = [];
  #selectionPoints = new Float32Array();
  #selectionRevision = 0;
  #dragStart: { x: number; y: number } | null = null;
  #dragEnd: { x: number; y: number } | null = null;
  #dragInteractionMode: ScMapInteractionMode | null = null;
  #dragTransform: Transform | null = null;
  #dragViewport: ScMapRegion | null = null;
  #rightPointerActive = false;
  #suppressNextContextMenu = false;
  #lassoPoints: ScMapPoint[] = [];
  #previewZoom: ScMapRegion | null = null;
  #wheelInteraction: "pan" | "zoom" | null = null;
  #wheelDeltaX = 0;
  #wheelDeltaY = 0;
  #wheelPoint: ScMapPoint | null = null;
  #wheelFrame: number | null = null;
  #wheelCommitTimer: ReturnType<typeof setTimeout> | null = null;
  #lastLoggedDataRevision = -1;
  #latestViewportRevision = 0;

  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = `
      :host { display:block; position:relative; width:100%; height:100%; overflow:hidden; }
      canvas { position:absolute; inset:0; display:block; width:100%; height:100%; }
      .background { z-index:0; pointer-events:none; }
      .points { z-index:1; pointer-events:none; }
      .overlay { z-index:2; touch-action:none; }
    `;
    this.#background = document.createElement("canvas");
    this.#background.className = "background";
    this.#pointsCanvas = document.createElement("canvas");
    this.#pointsCanvas.className = "points";
    this.#overlay = document.createElement("canvas");
    this.#overlay.className = "overlay";
    root.append(style, this.#background, this.#pointsCanvas, this.#overlay);
    this.#overlay.addEventListener("pointerdown", this.#onPointerDown);
    this.#overlay.addEventListener("pointermove", this.#onPointerMove);
    this.#overlay.addEventListener("pointerup", this.#onPointerUp);
    this.#overlay.addEventListener("pointercancel", this.#onPointerCancel);
    this.#overlay.addEventListener("wheel", this.#onWheel, { passive: false });
    this.#overlay.addEventListener("dblclick", this.#onDoubleClick);
    this.#overlay.addEventListener("contextmenu", this.#onContextMenu);
  }

  connectedCallback(): void {
    if (this.#worker) return;
    if (typeof OffscreenCanvas !== "function") {
      throw new Error("<sc-map> requires OffscreenCanvas support");
    }
    this.#pointsContext = this.#pointsCanvas.getContext("bitmaprenderer");
    if (!this.#pointsContext) {
      throw new Error("<sc-map> requires ImageBitmapRenderingContext support");
    }
    this.#worker = new ScMapRenderWorker();
    this.#worker.onerror = (event) => {
      const location = event.filename ? ` (${event.filename}:${event.lineno}:${event.colno})` : "";
      this.#reportError(
        "Rendering map canvas",
        event.error instanceof Error
          ? event.error
          : new Error(`${event.message || "Map render worker crashed"}${location}`),
      );
    };
    this.#worker.onmessage = (
      event: MessageEvent<{
        type: "render-stats";
        dataRevision: number;
        viewportRevision: number;
        pointCount: number;
        visiblePoints: number;
        imageMarkers: number;
        firstPoint: number[] | null;
        viewport: unknown;
        renderViewport: ScMapRenderViewport;
        bitmap: ImageBitmap;
      }>,
    ) => {
      if (event.data.type !== "render-stats") return;
      if (event.data.viewportRevision < this.#latestViewportRevision) {
        event.data.bitmap.close();
        return;
      }
      if (
        this.#pointsCanvas.width !== event.data.bitmap.width ||
        this.#pointsCanvas.height !== event.data.bitmap.height
      ) {
        this.#pointsCanvas.width = event.data.bitmap.width;
        this.#pointsCanvas.height = event.data.bitmap.height;
      }
      this.#pointsCanvas.style.left = `${-event.data.renderViewport.offsetX}px`;
      this.#pointsCanvas.style.top = `${-event.data.renderViewport.offsetY}px`;
      this.#pointsCanvas.style.width = `${event.data.renderViewport.renderWidth}px`;
      this.#pointsCanvas.style.height = `${event.data.renderViewport.renderHeight}px`;
      this.#pointsContext?.transferFromImageBitmap(event.data.bitmap);
      if (event.data.dataRevision === this.#lastLoggedDataRevision) return;
      this.#lastLoggedDataRevision = event.data.dataRevision;
      console.debug(
        "[sc-map:draw]",
        JSON.stringify({
          mode: this.#mode,
          ...event.data,
        }),
      );
    };
    this.#worker.postMessage({ type: "init" });
    this.#resizeObserver = new ResizeObserver(() => {
      this.#scheduleRender();
      this.#scheduleProjection();
    });
    this.#resizeObserver.observe(this);
    this.#postData();
    this.#renderAll();
    this.#scheduleDatasetLoad();
  }

  disconnectedCallback(): void {
    this.#resizeObserver?.disconnect();
    this.#resizeObserver = null;
    if (this.#frame !== null) cancelAnimationFrame(this.#frame);
    this.#frame = null;
    this.#cancelWheelGesture();
    this.#worker?.terminate();
    this.#worker = null;
    this.#pointsContext = null;
    this.#datasetRevision += 1;
    this.#projectionRevision += 1;
    this.#highlightResolutionRevision += 1;
    this.#arrowDataset?.dispose();
    this.#arrowDataset = null;
  }

  set arrowData(value: ArrayBuffer | readonly ArrayBuffer[] | null) {
    const current = this.#arrowData;
    if (
      value === current ||
      (Array.isArray(value) &&
        Array.isArray(current) &&
        value.length === current.length &&
        value.every((chunk, index) => chunk === current[index]))
    ) {
      return;
    }
    this.#arrowData = value;
    this.#scheduleDatasetLoad();
  }
  set legendColumn(value: string) {
    if (!value || value === this.#arrowLegendColumn) return;
    this.#arrowLegendColumn = value;
    this.#scheduleDatasetLoad();
  }
  set hiddenLegendKeys(value: string[]) {
    this.#hiddenLegendKeys = [...value];
    this.#scheduleProjection();
  }
  set points(value: number[] | Float32Array) {
    this.#points = value instanceof Float32Array ? value : Float32Array.from(value);
    this.#legendKeys = [];
    this.#postData();
  }
  set colorMap(value: Record<string, string>) {
    this.#colorMap = { ...value };
    this.#postData();
  }
  set showImageMarkers(value: boolean) {
    if (value === this.#showImageMarkers) return;
    this.#showImageMarkers = value;
    this.#postData();
  }
  set defectSize(value: number) {
    if (!Number.isFinite(value) || value <= 0) {
      throw new Error(`Invalid defect size: ${value}`);
    }
    if (value === this.#defectSize) return;
    this.#defectSize = value;
    this.#postData();
  }
  set mode(value: ScMapMode) {
    if (value === this.#mode) return;
    this.#cancelWheelGesture();
    this.#mode = value;
    this.#scheduleRender();
    this.#scheduleProjection();
  }
  set interactionMode(value: ScMapInteractionMode) {
    this.#interactionMode = value;
    this.#drawOverlay();
  }
  set zoom(value: ScMapRegion | null) {
    const next = value ? { ...value } : null;
    if (sameRegion(this.#zoom, next) && this.#previewZoom === null) return;
    this.#cancelWheelGesture();
    this.#zoom = next;
    this.#scheduleRender();
    this.#scheduleProjection();
  }
  set geometry(value: Partial<ScMapGeometry>) {
    this.#geometry = { ...DEFAULT_GEOMETRY, ...value };
    this.#scheduleRender();
    this.#scheduleProjection();
  }
  set highlightDefectIds(value: number[]) {
    this.#highlightDefectIds = [...new Set(value.filter(Number.isFinite))];
    this.#scheduleHighlightResolution();
  }
  set selectionDefectIds(value: number[]) {
    const next = [...new Set(value.filter(Number.isFinite))].sort((left, right) => left - right);
    if (
      next.length === this.#selectionIds.length &&
      next.every((id, index) => id === this.#selectionIds[index])
    ) {
      return;
    }
    this.#selectionIds = next;
    void this.#replaceSelectionIds().catch((error: unknown) => {
      this.#reportError("Hydrating map selection", error);
    });
  }
  set dataBounds(value: ScMapBounds | null) {
    this.#dataBounds = value ? { ...value } : null;
    this.#scheduleRender();
  }

  async updateSelection(command: MapSelectionCommand): Promise<number[]> {
    const dataset = this.#arrowDataset;
    if (!dataset) throw new Error("Map Arrow dataset is not ready");
    const revision = ++this.#selectionRevision;
    const result = await dataset.updateSelection(command, this.#projectionRequest());
    const ids = [...result.ids];
    if (dataset !== this.#arrowDataset || revision !== this.#selectionRevision) return ids;
    this.#selectionIds = ids;
    this.#selectionPoints = result.points;
    this.#drawOverlay();
    return ids;
  }

  clearSelection(): void {
    this.#selectionRevision += 1;
    this.#selectionIds = [];
    this.#selectionPoints = new Float32Array();
    this.#drawOverlay();
    const dataset = this.#arrowDataset;
    if (!dataset) return;
    const revision = this.#selectionRevision;
    void dataset
      .updateSelection(
        {
          operation: "clear",
          hiddenLegendKeys: this.#hiddenLegendKeys,
        },
        this.#projectionRequest(),
      )
      .then((result) => {
        if (dataset !== this.#arrowDataset || revision !== this.#selectionRevision) return;
        this.#selectionPoints = result.points;
        this.#drawOverlay();
      })
      .catch((error: unknown) => {
        if (dataset === this.#arrowDataset && revision === this.#selectionRevision) {
          this.#reportError("Clearing map selection", error);
        }
      });
  }

  async #replaceSelectionIds(): Promise<void> {
    const dataset = this.#arrowDataset;
    if (!dataset) {
      this.#selectionPoints = new Float32Array();
      this.#drawOverlay();
      return;
    }
    const revision = ++this.#selectionRevision;
    const result = await dataset.updateSelection(
      {
        operation: "replace",
        constraint: { kind: "ids", ids: this.#selectionIds },
        hiddenLegendKeys: this.#hiddenLegendKeys,
      },
      this.#projectionRequest(),
    );
    if (dataset !== this.#arrowDataset || revision !== this.#selectionRevision) return;
    this.#selectionIds = [...result.ids];
    this.#selectionPoints = result.points;
    this.#drawOverlay();
  }

  #modeBounds(): ScMapBounds {
    const geometry = this.#geometry;
    if (this.#mode === "wafer") {
      return {
        minX: geometry.centerX - geometry.waferRadiusNm,
        maxX: geometry.centerX + geometry.waferRadiusNm,
        minY: geometry.centerY - geometry.waferRadiusNm,
        maxY: geometry.centerY + geometry.waferRadiusNm,
      };
    }
    if (this.#mode === "die") {
      return { minX: 0, maxX: geometry.dieSizeX, minY: 0, maxY: geometry.dieSizeY };
    }
    return {
      minX: 0,
      maxX: geometry.dieSizeX * geometry.reticleXDieCount,
      minY: 0,
      maxY: geometry.dieSizeY * geometry.reticleYDieCount,
    };
  }

  #transform(): Transform {
    const width = Math.max(1, this.clientWidth);
    const height = Math.max(1, this.clientHeight);
    const region = this.#effectiveZoom();
    const bounds = region
      ? { minX: region.x, maxX: region.x + region.w, minY: region.y, maxY: region.y + region.h }
      : (this.#dataBounds ?? this.#modeBounds());
    const fitted = fitMapRegionToViewport(
      {
        x: bounds.minX,
        y: bounds.minY,
        w: bounds.maxX - bounds.minX || 1,
        h: bounds.maxY - bounds.minY || 1,
      },
      width,
      height,
    );
    return {
      scale: Math.min(width / fitted.w, height / fitted.h),
      centerX: width / 2,
      centerY: height / 2,
      offsetX: -(fitted.x + fitted.w / 2),
      offsetY: -(fitted.y + fitted.h / 2),
    };
  }

  #visibleRegion(): ScMapRegion {
    const width = Math.max(1, this.clientWidth);
    const height = Math.max(1, this.clientHeight);
    return fitMapRegionToViewport(this.#effectiveZoom() ?? this.#fullRegion(), width, height);
  }

  #effectiveZoom(): ScMapRegion | null {
    return this.#previewZoom ?? this.#zoom;
  }

  #fullRegion(): ScMapRegion {
    const bounds = this.#modeBounds();
    return {
      x: bounds.minX,
      y: bounds.minY,
      w: bounds.maxX - bounds.minX,
      h: bounds.maxY - bounds.minY,
    };
  }

  #toScreen(transform: Transform, x: number, y: number): [number, number] {
    return [
      transform.centerX + (x + transform.offsetX) * transform.scale,
      transform.centerY - (y + transform.offsetY) * transform.scale,
    ];
  }

  #toData(transform: Transform, x: number, y: number): [number, number] {
    return [
      (x - transform.centerX) / transform.scale - transform.offsetX,
      -(y - transform.centerY) / transform.scale - transform.offsetY,
    ];
  }

  #prepare(canvas: HTMLCanvasElement): CanvasRenderingContext2D {
    const dpr = window.devicePixelRatio || 1;
    const width = Math.max(1, this.clientWidth);
    const height = Math.max(1, this.clientHeight);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Canvas 2D context is unavailable");
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    context.clearRect(0, 0, width, height);
    return context;
  }

  #waferPath(x: number, y: number, radius: number): Path2D {
    const notchDepth = 6;
    const notchWidth = 12;
    const notchAngle = Math.asin(Math.min(notchWidth / 2 / radius, 1));
    const path = new Path2D();
    path.arc(x, y, radius, Math.PI / 2 + notchAngle, Math.PI / 2 - notchAngle, false);
    path.lineTo(x, y + radius - notchDepth);
    path.closePath();
    return path;
  }

  #drawWaferDieGrid(
    context: CanvasRenderingContext2D,
    transform: Transform,
    clipPath: Path2D | null,
  ): void {
    const geometry = this.#geometry;
    const visible = this.#visibleRegion();
    const minX = visible.x;
    const maxX = visible.x + visible.w;
    const minY = visible.y;
    const maxY = visible.y + visible.h;
    const dieWidth = Math.max(1, geometry.dieSizeX);
    const dieHeight = Math.max(1, geometry.dieSizeY);
    const ixStart = Math.floor((minX - geometry.originX) / dieWidth) - 1;
    const ixEnd = Math.ceil((maxX - geometry.originX) / dieWidth) + 1;
    const iyStart = Math.floor((minY - geometry.originY) / dieHeight) - 1;
    const iyEnd = Math.ceil((maxY - geometry.originY) / dieHeight) + 1;
    const totalCells = (ixEnd - ixStart + 1) * (iyEnd - iyStart + 1);

    context.save();
    if (clipPath) context.clip(clipPath);
    context.fillStyle = "#e8e8e8";
    context.fillRect(0, 0, Math.max(1, this.clientWidth), Math.max(1, this.clientHeight));

    if (
      totalCells <= 50_000 &&
      (dieWidth * transform.scale >= 0.5 || dieHeight * transform.scale >= 0.5)
    ) {
      const radius = geometry.waferRadiusNm;
      for (let ix = ixStart; ix <= ixEnd; ix += 1) {
        for (let iy = iyStart; iy <= iyEnd; iy += 1) {
          const left = geometry.originX + ix * dieWidth;
          const top = geometry.originY + iy * dieHeight;
          const right = left + dieWidth;
          const bottom = top + dieHeight;
          const nearestX = Math.max(left, Math.min(geometry.centerX, right));
          const nearestY = Math.max(top, Math.min(geometry.centerY, bottom));
          if (Math.hypot(nearestX - geometry.centerX, nearestY - geometry.centerY) > radius) {
            continue;
          }
          const valid =
            Math.max(
              Math.hypot(left - geometry.centerX, top - geometry.centerY),
              Math.hypot(right - geometry.centerX, top - geometry.centerY),
              Math.hypot(left - geometry.centerX, bottom - geometry.centerY),
              Math.hypot(right - geometry.centerX, bottom - geometry.centerY),
            ) <= radius;
          const [screenLeft, screenBottom] = this.#toScreen(transform, left, top);
          const screenWidth = dieWidth * transform.scale;
          const screenHeight = dieHeight * transform.scale;
          const pixelLeft = Math.round(screenLeft);
          const pixelRight = Math.round(screenLeft + screenWidth);
          const pixelTop = Math.round(screenBottom - screenHeight);
          const pixelBottom = Math.round(screenBottom);
          context.fillStyle = valid ? "#ffffff" : "#9ca3af";
          context.fillRect(pixelLeft, pixelTop, pixelRight - pixelLeft, pixelBottom - pixelTop);
        }
      }
    }

    context.beginPath();
    context.strokeStyle = "#9ca3af";
    context.lineWidth = 1;
    for (let ix = ixStart; ix <= ixEnd + 1; ix += 1) {
      const [screenX] = this.#toScreen(transform, geometry.originX + ix * dieWidth, 0);
      const [, screenTop] = this.#toScreen(transform, 0, maxY);
      const [, screenBottom] = this.#toScreen(transform, 0, minY);
      context.moveTo(Math.round(screenX) + 0.5, screenTop);
      context.lineTo(Math.round(screenX) + 0.5, screenBottom);
    }
    for (let iy = iyStart; iy <= iyEnd + 1; iy += 1) {
      const [, screenY] = this.#toScreen(transform, 0, geometry.originY + iy * dieHeight);
      const [screenLeft] = this.#toScreen(transform, minX, 0);
      const [screenRight] = this.#toScreen(transform, maxX, 0);
      context.moveTo(screenLeft, Math.round(screenY) + 0.5);
      context.lineTo(screenRight, Math.round(screenY) + 0.5);
    }
    context.stroke();
    context.restore();
  }

  #drawBackground(): void {
    const context = this.#prepare(this.#background);
    const transform = this.#transform();
    const geometry = this.#geometry;
    const width = Math.max(1, this.clientWidth);
    const height = Math.max(1, this.clientHeight);
    if (this.#mode === "wafer") {
      const [x, y] = this.#toScreen(transform, geometry.centerX, geometry.centerY);
      const radius = geometry.waferRadiusNm * transform.scale;
      if (this.#effectiveZoom()) {
        this.#drawWaferDieGrid(context, transform, null);
        context.strokeStyle = "#333333";
        context.lineWidth = 2;
        context.strokeRect(1, 1, width - 2, height - 2);
        return;
      }
      const waferPath = this.#waferPath(x, y, radius);
      context.save();
      context.shadowColor = "rgba(0,0,0,0.12)";
      context.shadowBlur = 10;
      context.shadowOffsetY = 3;
      context.fillStyle = "#ffffff";
      context.fill(waferPath);
      context.restore();
      this.#drawWaferDieGrid(context, transform, waferPath);
      context.strokeStyle = "#333333";
      context.lineWidth = 2;
      context.stroke(waferPath);
      return;
    }
    context.fillStyle = "#e8e8e8";
    context.fillRect(0, 0, width, height);
    const xCount = this.#mode === "reticle" ? geometry.reticleXDieCount : 1;
    const yCount = this.#mode === "reticle" ? geometry.reticleYDieCount : 1;
    const dieWidth = Math.max(1, geometry.dieSizeX);
    const dieHeight = Math.max(1, geometry.dieSizeY);
    const [outerLeft, outerBottom] = this.#toScreen(transform, 0, 0);
    const [outerRight, outerTop] = this.#toScreen(transform, xCount * dieWidth, yCount * dieHeight);
    const clipLeft = Math.min(outerLeft, outerRight);
    const clipTop = Math.min(outerTop, outerBottom);
    const clipWidth = Math.abs(outerRight - outerLeft);
    const clipHeight = Math.abs(outerBottom - outerTop);
    context.save();
    context.beginPath();
    context.rect(clipLeft, clipTop, clipWidth, clipHeight);
    context.clip();
    for (let ix = 0; ix < xCount; ix += 1) {
      for (let iy = 0; iy < yCount; iy += 1) {
        const [left, bottom] = this.#toScreen(transform, ix * dieWidth, iy * dieHeight);
        const [right, top] = this.#toScreen(transform, (ix + 1) * dieWidth, (iy + 1) * dieHeight);
        const x = Math.min(left, right);
        const y = Math.min(top, bottom);
        const w = Math.abs(right - left);
        const h = Math.abs(bottom - top);
        context.fillStyle = "#ffffff";
        context.fillRect(x, y, w, h);
        context.strokeStyle = "#9ca3af";
        context.lineWidth = 1;
        context.strokeRect(Math.round(x) + 0.5, Math.round(y) + 0.5, w, h);
      }
    }
    context.restore();
    context.strokeStyle = "#333333";
    context.lineWidth = 2;
    context.strokeRect(clipLeft, clipTop, clipWidth, clipHeight);
  }

  #drawOverlay(): void {
    const context = this.#prepare(this.#overlay);
    const transform = this.#transform();
    const coordinate = (item: ScMapHighlight): [number, number] =>
      this.#mode === "wafer"
        ? [item.waferX, item.waferY]
        : this.#mode === "die"
          ? [item.dieX, item.dieY]
          : [item.reticleX, item.reticleY];
    const drawCrosshairs = (items: Array<[number, number]>, color: string) => {
      context.beginPath();
      context.strokeStyle = color;
      for (const [dataX, dataY] of items) {
        const [x, y] = this.#toScreen(transform, dataX, dataY);
        context.moveTo(x - 3, y);
        context.lineTo(x + 3, y);
        context.moveTo(x, y - 3);
        context.lineTo(x, y + 3);
      }
      context.stroke();
    };
    const drawFlatCrosshairs = (points: Float32Array, color: string) => {
      context.beginPath();
      context.strokeStyle = color;
      for (let offset = 0; offset < points.length; offset += 2) {
        const [x, y] = this.#toScreen(transform, points[offset], points[offset + 1]);
        context.moveTo(x - 3, y);
        context.lineTo(x + 3, y);
        context.moveTo(x, y - 3);
        context.lineTo(x, y + 3);
      }
      context.stroke();
    };
    drawCrosshairs(this.#highlights.map(coordinate), "#A855F7");
    drawFlatCrosshairs(this.#selectionPoints, "#000000");
    const dragInteractionMode = this.#dragInteractionMode ?? this.#interactionMode;
    if (dragInteractionMode === "lasso" && this.#lassoPoints.length > 1) {
      context.beginPath();
      context.moveTo(this.#lassoPoints[0].x, this.#lassoPoints[0].y);
      for (const point of this.#lassoPoints.slice(1)) {
        context.lineTo(point.x, point.y);
      }
      context.closePath();
      context.fillStyle = "rgba(168,85,247,.15)";
      context.strokeStyle = "#a855f7";
      context.fill();
      context.stroke();
    } else if (this.#dragStart && this.#dragEnd && dragInteractionMode !== "pan") {
      const x = Math.min(this.#dragStart.x, this.#dragEnd.x);
      const y = Math.min(this.#dragStart.y, this.#dragEnd.y);
      const w = Math.abs(this.#dragEnd.x - this.#dragStart.x);
      const h = Math.abs(this.#dragEnd.y - this.#dragStart.y);
      context.fillStyle =
        dragInteractionMode === "zoomin" ? "rgba(34,197,94,.15)" : "rgba(59,130,246,.15)";
      context.strokeStyle = dragInteractionMode === "zoomin" ? "#22c55e" : "#3b82f6";
      context.fillRect(x, y, w, h);
      context.strokeRect(x, y, w, h);
    }
  }

  #emitProgress(progress: number, stage: string): void {
    this.dispatchEvent(
      new CustomEvent<ScMapProgress>("map-progress", {
        detail: { progress, stage },
        bubbles: true,
        composed: true,
      }),
    );
  }

  #reportError(context: string, cause: unknown): void {
    const error = cause instanceof Error ? cause : new Error(String(cause));
    console.error(`[sc-map] ${context}`, error);
    this.dispatchEvent(
      new CustomEvent<ScMapErrorDetail>("map-error", {
        detail: {
          context,
          message: error.message,
          ...(error.stack ? { stack: error.stack } : {}),
        },
        bubbles: true,
        composed: true,
      }),
    );
  }

  #scheduleDatasetLoad(): void {
    if (this.#datasetLoadScheduled) return;
    this.#datasetLoadScheduled = true;
    queueMicrotask(() => {
      this.#datasetLoadScheduled = false;
      void this.#loadArrowDataset();
    });
  }

  #scheduleHighlightResolution(): void {
    this.#highlightResolutionRevision += 1;
    if (this.#highlightResolutionScheduled) return;
    this.#highlightResolutionScheduled = true;
    queueMicrotask(() => {
      this.#highlightResolutionScheduled = false;
      void this.#resolveHighlightRows();
    });
  }

  async #resolveHighlightRows(): Promise<void> {
    const dataset = this.#arrowDataset;
    const revision = this.#highlightResolutionRevision;
    if (!dataset) {
      this.#highlights = [];
      this.#drawOverlay();
      return;
    }
    const ids = [...this.#highlightDefectIds];
    try {
      const resolved = await dataset.resolveHighlights(ids);
      if (dataset !== this.#arrowDataset || revision !== this.#highlightResolutionRevision) return;
      const highlightIds = new Set(this.#highlightDefectIds);
      this.#highlights = resolved.filter((item) => highlightIds.has(item.defectId));
      this.#drawOverlay();
    } catch (error) {
      if (dataset !== this.#arrowDataset || revision !== this.#highlightResolutionRevision) return;
      this.#reportError("Resolving map highlights", error);
    }
  }

  async #loadArrowDataset(): Promise<void> {
    const arrow = this.#arrowData;
    const revision = ++this.#datasetRevision;
    this.#projectionRevision += 1;
    this.#arrowDataset?.dispose();
    this.#arrowDataset = null;
    this.#highlights = [];
    this.#selectionPoints = new Float32Array();
    this.#points = new Float32Array();
    this.#legendKeys = [];
    this.#postData();
    this.#drawOverlay();
    if (!arrow || !this.isConnected) return;

    this.#emitProgress(0, "Loading Arrow table in map worker");
    try {
      const dataset = await createMapArrowDataset(
        arrow,
        this.#arrowLegendColumn,
        (progress, stage) => this.#emitProgress(progress * 0.5, stage),
      );
      if (revision !== this.#datasetRevision || !this.isConnected) {
        dataset.dispose();
        return;
      }
      this.#arrowDataset = dataset;
      if (this.#selectionIds.length > 0) {
        const selectionRevision = ++this.#selectionRevision;
        const selection = await dataset.updateSelection(
          {
            operation: "replace",
            constraint: { kind: "ids", ids: this.#selectionIds },
            hiddenLegendKeys: this.#hiddenLegendKeys,
          },
          this.#projectionRequest(),
        );
        if (
          dataset !== this.#arrowDataset ||
          revision !== this.#datasetRevision ||
          selectionRevision !== this.#selectionRevision
        ) {
          return;
        }
        this.#selectionIds = [...selection.ids];
        this.#selectionPoints = selection.points;
        this.#drawOverlay();
      }
      this.#scheduleHighlightResolution();
      this.#scheduleProjection();
    } catch (error) {
      if (revision !== this.#datasetRevision) return;
      this.#reportError("Loading Arrow map dataset", error);
    }
  }

  #projectionRequest(): MapProjectionSpec {
    const width = Math.max(1, this.clientWidth);
    const height = Math.max(1, this.clientHeight);
    const zoom = this.#zoom ? fitMapRegionToViewport(this.#zoom, width, height) : null;
    const bounds = zoom
      ? {
          minX: zoom.x,
          maxX: zoom.x + zoom.w,
          minY: zoom.y,
          maxY: zoom.y + zoom.h,
        }
      : this.#modeBounds();
    return {
      mode: this.#mode,
      binSize: Math.max((bounds.maxX - bounds.minX) / width, (bounds.maxY - bounds.minY) / height),
      zoom,
      hiddenLegendKeys: [...this.#hiddenLegendKeys],
    };
  }

  #scheduleProjection(): void {
    this.#projectionRevision += 1;
    if (!this.#arrowDataset || this.#projectionRunning || !this.isConnected) return;
    void this.#projectArrowRows();
  }

  async #projectArrowRows(): Promise<void> {
    if (!this.#arrowDataset || this.#projectionRunning) return;
    this.#projectionRunning = true;
    try {
      while (this.#arrowDataset) {
        const revision = this.#projectionRevision;
        const selectionRevision = this.#selectionRevision;
        const dataset: MapArrowDataset = this.#arrowDataset;
        const mode = this.#mode;
        this.#emitProgress(0.5, `${mode}: preparing projection`);
        const projection = await dataset.project(
          this.#projectionRequest(),
          (progress: number, stage: string) => this.#emitProgress(0.5 + progress * 0.5, stage),
        );
        if (dataset !== this.#arrowDataset) continue;
        if (revision !== this.#projectionRevision) continue;
        this.#points = projection.points;
        if (selectionRevision === this.#selectionRevision) {
          this.#selectionPoints = projection.selectionPoints;
        }
        this.#legendKeys = projection.legendKeys;
        this.#postData();
        this.#renderAll();
        this.#emitProgress(1, "Map ready");
        this.dispatchEvent(
          new CustomEvent("map-ready", {
            detail: { mode, binCount: Math.floor(projection.points.length / 6) },
            bubbles: true,
            composed: true,
          }),
        );
        break;
      }
    } catch (error) {
      if (this.#arrowDataset) {
        this.#reportError("Projecting Arrow map rows", error);
      }
    } finally {
      this.#projectionRunning = false;
    }
  }

  #postData(): void {
    if (!this.#worker) return;
    const points = this.#points.slice();
    this.#worker.postMessage(
      {
        type: "data",
        points,
        colorMap: encodeLegendColorMap(this.#colorMap, this.#legendKeys),
        showImageMarkers: this.#showImageMarkers,
        defectSize: this.#defectSize,
      },
      [points.buffer],
    );
  }

  #scheduleRender(): void {
    if (!this.#worker) return;
    if (this.#frame !== null) cancelAnimationFrame(this.#frame);
    this.#frame = requestAnimationFrame(() => {
      this.#frame = null;
      this.#renderAll();
    });
  }

  #renderAll(): void {
    this.#drawBackground();
    this.#drawOverlay();
    if (!this.#worker) return;
    const bounds = this.#dataBounds ?? this.#modeBounds();
    const zoom = this.#effectiveZoom();
    const viewportRevision = ++this.#latestViewportRevision;
    this.#worker.postMessage({
      type: "viewport",
      viewportRevision,
      viewport: {
        width: Math.max(1, this.clientWidth),
        height: Math.max(1, this.clientHeight),
        dpr: window.devicePixelRatio || 1,
        centerX: (bounds.minX + bounds.maxX) / 2,
        centerY: (bounds.minY + bounds.maxY) / 2,
        dataRangeNm: Math.max(bounds.maxX - bounds.minX, bounds.maxY - bounds.minY),
        zoom: zoom ? { ...zoom } : null,
        dataBounds: { ...bounds },
      },
    });
  }

  #localPoint(event: MouseEvent): { x: number; y: number } {
    const rect = this.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  #onContextMenu = (event: MouseEvent): void => {
    event.preventDefault();
    if (this.#suppressNextContextMenu) {
      this.#suppressNextContextMenu = false;
      return;
    }
    this.dispatchEvent(
      new CustomEvent("map-context-menu", {
        detail: { x: event.clientX, y: event.clientY },
        bubbles: true,
      }),
    );
  };

  #onPointerDown = (event: PointerEvent): void => {
    if (event.button !== 0 && event.button !== 2) return;
    this.#flushWheelGesture();
    if (event.button === 2) event.preventDefault();
    this.#rightPointerActive = event.button === 2;
    this.#suppressNextContextMenu = false;
    this.#overlay.setPointerCapture?.(event.pointerId);
    this.#dragStart = this.#localPoint(event);
    this.#dragEnd = { ...this.#dragStart };
    this.#dragInteractionMode = event.button === 2 ? "pan" : this.#interactionMode;
    this.#dragTransform = this.#dragInteractionMode === "pan" ? this.#transform() : null;
    this.#dragViewport =
      this.#dragInteractionMode === "pan" ? (this.#effectiveZoom() ?? this.#fullRegion()) : null;
    this.#lassoPoints = this.#dragInteractionMode === "lasso" ? [{ ...this.#dragStart }] : [];
    this.#drawOverlay();
  };

  #onPointerMove = (event: PointerEvent): void => {
    if (!this.#dragStart) return;
    this.#dragEnd = this.#localPoint(event);
    if (
      this.#rightPointerActive &&
      Math.hypot(this.#dragEnd.x - this.#dragStart.x, this.#dragEnd.y - this.#dragStart.y) >= 4
    ) {
      this.#suppressNextContextMenu = true;
    }
    if (this.#dragInteractionMode === "pan" && this.#dragTransform && this.#dragViewport) {
      const [startX, startY] = this.#toData(
        this.#dragTransform,
        this.#dragStart.x,
        this.#dragStart.y,
      );
      const [endX, endY] = this.#toData(this.#dragTransform, this.#dragEnd.x, this.#dragEnd.y);
      this.#previewZoom = clampRegionToBounds(
        {
          x: this.#dragViewport.x + startX - endX,
          y: this.#dragViewport.y + startY - endY,
          w: this.#dragViewport.w,
          h: this.#dragViewport.h,
        },
        this.#fullRegion(),
      );
      this.#scheduleRender();
    } else if (this.#dragInteractionMode === "lasso") {
      const previous = this.#lassoPoints.at(-1);
      if (
        !previous ||
        Math.hypot(this.#dragEnd.x - previous.x, this.#dragEnd.y - previous.y) >= 2
      ) {
        this.#lassoPoints.push({ ...this.#dragEnd });
      }
    } else if (this.#dragInteractionMode === "zoomin") {
      const width = Math.max(1, this.clientWidth);
      const height = Math.max(1, this.clientHeight);
      const dx = this.#dragEnd.x - this.#dragStart.x;
      const dy = this.#dragEnd.y - this.#dragStart.y;
      const signX = Math.sign(dx) || 1;
      const signY = Math.sign(dy) || 1;
      if (Math.abs(dx / dy) > width / height) {
        this.#dragEnd.y = this.#dragStart.y + (signY * (Math.abs(dx) * height)) / width;
      } else {
        this.#dragEnd.x = this.#dragStart.x + (signX * (Math.abs(dy) * width)) / height;
      }
    }
    this.#drawOverlay();
  };

  #onPointerUp = (event: PointerEvent): void => {
    if (!this.#dragStart || !this.#dragEnd) return;
    const start = this.#dragStart;
    const end = this.#dragEnd;
    const lassoPoints = this.#lassoPoints;
    const dragInteractionMode = this.#dragInteractionMode;
    const dragViewport = this.#dragViewport;
    this.#rightPointerActive = false;
    this.#dragStart = null;
    this.#dragEnd = null;
    this.#dragInteractionMode = null;
    this.#dragTransform = null;
    this.#dragViewport = null;
    this.#lassoPoints = [];
    const transform = this.#transform();
    const [startX, startY] = this.#toData(transform, start.x, start.y);
    const [endX, endY] = this.#toData(transform, end.x, end.y);
    const dx = Math.abs(end.x - start.x);
    const dy = Math.abs(end.y - start.y);
    if (dragInteractionMode === "lasso" && lassoPoints.length >= 3) {
      const dataPoints = lassoPoints.map((point) => this.#toData(transform, point.x, point.y));
      const points = dataPoints.map(([x, y]) => ({ x, y }));
      const xs = points.map((point) => point.x);
      const ys = points.map((point) => point.y);
      const region = {
        x: Math.min(...xs),
        y: Math.min(...ys),
        w: Math.max(...xs) - Math.min(...xs),
        h: Math.max(...ys) - Math.min(...ys),
      };
      this.dispatchEvent(
        new CustomEvent<ScMapLassoSelection>("lasso-select", {
          detail: { points, region },
          bubbles: true,
        }),
      );
    } else if (dx >= 4 || dy >= 4) {
      if (dragInteractionMode === "pan") {
        const preview = this.#previewZoom ?? dragViewport ?? this.#fullRegion();
        const next = sameRegion(preview, this.#fullRegion()) ? null : { ...preview };
        this.#previewZoom = null;
        this.#zoom = next;
        this.#scheduleRender();
        this.#scheduleProjection();
        this.dispatchEvent(
          new CustomEvent("zoom-in", {
            detail: next,
            bubbles: true,
          }),
        );
      } else {
        const region = {
          x: Math.min(startX, endX),
          y: Math.min(startY, endY),
          w: Math.abs(endX - startX),
          h: Math.abs(endY - startY),
        };
        if (dragInteractionMode === "zoomin") {
          this.dispatchEvent(new CustomEvent("zoom-in", { detail: region, bubbles: true }));
        } else {
          this.dispatchEvent(new CustomEvent("box-select", { detail: region, bubbles: true }));
        }
      }
    }
    if (dragInteractionMode === "pan" && this.#previewZoom !== null) {
      this.#previewZoom = null;
      this.#scheduleRender();
    }
    this.#drawOverlay();
  };

  #onPointerCancel = (): void => {
    this.#rightPointerActive = false;
    this.#suppressNextContextMenu = false;
    this.#dragStart = null;
    this.#dragEnd = null;
    this.#dragInteractionMode = null;
    this.#dragTransform = null;
    this.#dragViewport = null;
    this.#lassoPoints = [];
    this.#previewZoom = null;
    this.#scheduleRender();
    this.#drawOverlay();
  };

  #onWheel = (event: WheelEvent): void => {
    const interaction = event.ctrlKey ? "zoom" : "pan";
    const deltaX = normalizeWheelDelta(event.deltaX, event.deltaMode, this.clientWidth);
    const deltaY = normalizeWheelDelta(event.deltaY, event.deltaMode, this.clientHeight);
    if (deltaX === 0 && deltaY === 0) return;
    if (this.#wheelInteraction !== null && this.#wheelInteraction !== interaction) {
      this.#flushWheelGesture();
    }
    event.preventDefault();
    this.#wheelInteraction = interaction;
    this.#wheelDeltaX += deltaX;
    this.#wheelDeltaY += deltaY;
    this.#wheelPoint = this.#localPoint(event);
    if (this.#wheelFrame === null) {
      this.#wheelFrame = requestAnimationFrame(this.#applyWheelDelta);
    }
    if (this.#wheelCommitTimer !== null) clearTimeout(this.#wheelCommitTimer);
    this.#wheelCommitTimer = setTimeout(this.#flushWheelGesture, SC_MAP_WHEEL_ZOOM_COMMIT_DELAY_MS);
  };

  #applyWheelDelta = (): void => {
    this.#wheelFrame = null;
    if (!this.#wheelPoint || this.#wheelInteraction === null) return;

    if (this.#wheelInteraction === "pan") {
      const deltaX = this.#wheelDeltaX;
      const deltaY = this.#wheelDeltaY;
      this.#wheelDeltaX = 0;
      this.#wheelDeltaY = 0;
      this.#applyWheelPan(deltaX, deltaY);
      return;
    }
    if (this.#wheelDeltaY === 0) return;

    const minDelta = Math.log(MIN_WHEEL_FRAME_FACTOR) / SC_MAP_WHEEL_ZOOM_SENSITIVITY;
    const maxDelta = Math.log(MAX_WHEEL_FRAME_FACTOR) / SC_MAP_WHEEL_ZOOM_SENSITIVITY;
    const delta = Math.min(maxDelta, Math.max(minDelta, this.#wheelDeltaY));
    this.#wheelDeltaY -= delta;
    this.#wheelDeltaX = 0;
    this.#applyWheelZoom(delta);
    if (Math.abs(this.#wheelDeltaY) > Number.EPSILON && this.#wheelFrame === null) {
      this.#wheelFrame = requestAnimationFrame(this.#applyWheelDelta);
    }
  };

  #applyWheelPan(deltaX: number, deltaY: number): void {
    if (deltaX === 0 && deltaY === 0) return;
    const current = this.#effectiveZoom() ?? this.#fullRegion();
    const transform = this.#transform();
    const next = clampRegionToBounds(
      {
        x: current.x + deltaX / transform.scale,
        y: current.y - deltaY / transform.scale,
        w: current.w,
        h: current.h,
      },
      this.#fullRegion(),
    );
    if (!sameRegion(current, next)) {
      this.#previewZoom = next;
      this.#scheduleRender();
    }
  }

  #applyWheelZoom(delta: number): void {
    const point = this.#wheelPoint;
    if (!point || delta === 0) return;
    const current = this.#effectiveZoom() ?? this.#fullRegion();
    const transform = this.#transform();
    const [anchorX, anchorY] = this.#toData(transform, point.x, point.y);
    const exponent = Math.min(
      -Math.log(MIN_VIEWPORT_RATIO),
      Math.max(Math.log(MIN_VIEWPORT_RATIO), delta * SC_MAP_WHEEL_ZOOM_SENSITIVITY),
    );
    const factor = Math.exp(exponent);
    const next = zoomRegionAroundPoint(
      current,
      this.#fullRegion(),
      { x: anchorX, y: anchorY },
      factor,
    );
    if (!sameRegion(current, next)) {
      this.#previewZoom = next;
      this.#scheduleRender();
    }
  }

  #flushWheelGesture = (): void => {
    if (this.#wheelFrame !== null) {
      cancelAnimationFrame(this.#wheelFrame);
      this.#wheelFrame = null;
    }
    if (this.#wheelInteraction === "pan") {
      this.#applyWheelPan(this.#wheelDeltaX, this.#wheelDeltaY);
    } else if (Math.abs(this.#wheelDeltaY) > Number.EPSILON) {
      this.#applyWheelZoom(this.#wheelDeltaY);
    }
    this.#wheelDeltaX = 0;
    this.#wheelDeltaY = 0;
    if (this.#wheelCommitTimer !== null) {
      clearTimeout(this.#wheelCommitTimer);
      this.#wheelCommitTimer = null;
    }
    const preview = this.#previewZoom;
    if (!preview) {
      this.#wheelInteraction = null;
      return;
    }
    const next = sameRegion(preview, this.#fullRegion()) ? null : { ...preview };
    this.#previewZoom = null;
    this.#wheelInteraction = null;
    this.#zoom = next;
    this.#scheduleRender();
    this.#scheduleProjection();
    this.dispatchEvent(new CustomEvent("zoom-in", { detail: next, bubbles: true }));
  };

  #cancelWheelGesture(): void {
    if (this.#wheelFrame !== null) cancelAnimationFrame(this.#wheelFrame);
    if (this.#wheelCommitTimer !== null) clearTimeout(this.#wheelCommitTimer);
    this.#wheelFrame = null;
    this.#wheelCommitTimer = null;
    this.#wheelInteraction = null;
    this.#wheelDeltaX = 0;
    this.#wheelDeltaY = 0;
    this.#wheelPoint = null;
    this.#previewZoom = null;
  }

  #onDoubleClick = (): void => {
    this.clearSelection();
    this.dispatchEvent(new CustomEvent("clear-selection", { bubbles: true }));
    this.#drawOverlay();
  };
}

export function defineScMapElement(): void {
  if (!customElements.get(SC_MAP_TAG_NAME)) customElements.define(SC_MAP_TAG_NAME, ScMapElement);
}
