import type { ScMapBounds, ScMapRegion } from "./types";
import {
  createMapArrowDataset,
  type MapArrowDataset,
  type MapProjectionSpec,
} from "./map-arrow-client";
import ScMapRenderWorker from "./sc-map-render.worker?worker&inline";

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
  #immediateDefectIds: number[] = [];
  #resolvedImmediateHighlights: ScMapHighlight[] = [];
  #highlightResolutionRevision = 0;
  #highlightResolutionScheduled = false;
  #immediatePoints: Array<{ x: number; y: number }> = [];
  #dragStart: { x: number; y: number } | null = null;
  #dragEnd: { x: number; y: number } | null = null;
  #lassoPoints: ScMapPoint[] = [];
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
    this.#overlay.addEventListener("pointercancel", this.#onPointerUp);
    this.#overlay.addEventListener("dblclick", this.#onDoubleClick);
    this.#overlay.addEventListener("contextmenu", (event) => event.preventDefault());
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
    this.#mode = value;
    this.#scheduleRender();
    this.#scheduleProjection();
  }
  set interactionMode(value: ScMapInteractionMode) {
    this.#interactionMode = value;
    this.#drawOverlay();
  }
  set zoom(value: ScMapRegion | null) {
    this.#zoom = value ? { ...value } : null;
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
  set immediateDefectIds(value: number[]) {
    this.#immediateDefectIds = [...new Set(value.filter(Number.isFinite))];
    this.#scheduleHighlightResolution();
  }
  set immediatePoints(value: Array<{ x: number; y: number }>) {
    this.#immediatePoints = value.map((point) => ({ ...point }));
    this.#drawOverlay();
  }
  set dataBounds(value: ScMapBounds | null) {
    this.#dataBounds = value ? { ...value } : null;
    this.#scheduleRender();
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
    const region = this.#zoom;
    const bounds = region
      ? { minX: region.x, maxX: region.x + region.w, minY: region.y, maxY: region.y + region.h }
      : (this.#dataBounds ?? this.#modeBounds());
    return {
      scale: Math.min(
        width / (bounds.maxX - bounds.minX || 1),
        height / (bounds.maxY - bounds.minY || 1),
      ),
      centerX: width / 2,
      centerY: height / 2,
      offsetX: -(bounds.minX + bounds.maxX) / 2,
      offsetY: -(bounds.minY + bounds.maxY) / 2,
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
    const zoom = this.#zoom;
    const minX = zoom ? zoom.x : geometry.centerX - geometry.waferRadiusNm;
    const maxX = zoom ? zoom.x + zoom.w : geometry.centerX + geometry.waferRadiusNm;
    const minY = zoom ? zoom.y : geometry.centerY - geometry.waferRadiusNm;
    const maxY = zoom ? zoom.y + zoom.h : geometry.centerY + geometry.waferRadiusNm;
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
      if (this.#zoom) {
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
    const bounds = this.#zoom
      ? {
          minX: this.#zoom.x,
          maxX: this.#zoom.x + this.#zoom.w,
          minY: this.#zoom.y,
          maxY: this.#zoom.y + this.#zoom.h,
        }
      : this.#modeBounds();
    const cellX = this.#mode === "reticle" ? geometry.dieSizeX : geometry.dieSizeX;
    const cellY = this.#mode === "reticle" ? geometry.dieSizeY : geometry.dieSizeY;
    if (cellX * transform.scale >= 2 || cellY * transform.scale >= 2) {
      context.beginPath();
      context.strokeStyle = "#9ca3af";
      context.lineWidth = 1;
      for (let x = Math.floor(bounds.minX / cellX) * cellX; x <= bounds.maxX; x += cellX) {
        const [screenX] = this.#toScreen(transform, x, 0);
        context.moveTo(Math.round(screenX) + 0.5, 0);
        context.lineTo(Math.round(screenX) + 0.5, height);
      }
      for (let y = Math.floor(bounds.minY / cellY) * cellY; y <= bounds.maxY; y += cellY) {
        const [, screenY] = this.#toScreen(transform, 0, y);
        context.moveTo(0, Math.round(screenY) + 0.5);
        context.lineTo(width, Math.round(screenY) + 0.5);
      }
      context.stroke();
    }
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
    drawCrosshairs(this.#highlights.map(coordinate), "#A855F7");
    drawCrosshairs(
      [
        ...this.#resolvedImmediateHighlights.map(coordinate),
        ...this.#immediatePoints.map((point) => [point.x, point.y] as [number, number]),
      ],
      "#000000",
    );
    if (this.#interactionMode === "lasso" && this.#lassoPoints.length > 1) {
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
    } else if (this.#dragStart && this.#dragEnd && this.#interactionMode !== "pan") {
      const x = Math.min(this.#dragStart.x, this.#dragEnd.x);
      const y = Math.min(this.#dragStart.y, this.#dragEnd.y);
      const w = Math.abs(this.#dragEnd.x - this.#dragStart.x);
      const h = Math.abs(this.#dragEnd.y - this.#dragStart.y);
      context.fillStyle =
        this.#interactionMode === "zoomin" ? "rgba(34,197,94,.15)" : "rgba(59,130,246,.15)";
      context.strokeStyle = this.#interactionMode === "zoomin" ? "#22c55e" : "#3b82f6";
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
      this.#resolvedImmediateHighlights = [];
      this.#drawOverlay();
      return;
    }
    const ids = [...new Set([...this.#highlightDefectIds, ...this.#immediateDefectIds])];
    try {
      const resolved = await dataset.resolveHighlights(ids);
      if (dataset !== this.#arrowDataset || revision !== this.#highlightResolutionRevision) return;
      const highlightIds = new Set(this.#highlightDefectIds);
      const immediateIds = new Set(this.#immediateDefectIds);
      this.#highlights = resolved.filter((item) => highlightIds.has(item.defectId));
      this.#resolvedImmediateHighlights = resolved.filter((item) =>
        immediateIds.has(item.defectId),
      );
      this.#drawOverlay();
    } catch (error) {
      if (dataset !== this.#arrowDataset || revision !== this.#highlightResolutionRevision) return;
      this.dispatchEvent(
        new CustomEvent("map-error", {
          detail: error instanceof Error ? error.message : String(error),
          bubbles: true,
          composed: true,
        }),
      );
    }
  }

  async #loadArrowDataset(): Promise<void> {
    const arrow = this.#arrowData;
    const revision = ++this.#datasetRevision;
    this.#projectionRevision += 1;
    this.#arrowDataset?.dispose();
    this.#arrowDataset = null;
    this.#highlights = [];
    this.#resolvedImmediateHighlights = [];
    this.#points = new Float32Array();
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
      this.#scheduleHighlightResolution();
      this.#scheduleProjection();
    } catch (error) {
      if (revision !== this.#datasetRevision) return;
      this.dispatchEvent(
        new CustomEvent("map-error", {
          detail: error instanceof Error ? error.message : String(error),
          bubbles: true,
          composed: true,
        }),
      );
    }
  }

  #projectionRequest(): MapProjectionSpec {
    const bounds = this.#zoom
      ? {
          minX: this.#zoom.x,
          maxX: this.#zoom.x + this.#zoom.w,
          minY: this.#zoom.y,
          maxY: this.#zoom.y + this.#zoom.h,
        }
      : this.#modeBounds();
    const width = Math.max(1, this.clientWidth);
    const height = Math.max(1, this.clientHeight);
    return {
      mode: this.#mode,
      binSize: Math.max((bounds.maxX - bounds.minX) / width, (bounds.maxY - bounds.minY) / height),
      zoom: this.#zoom ? { ...this.#zoom } : null,
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
        const dataset: MapArrowDataset = this.#arrowDataset;
        const mode = this.#mode;
        this.#emitProgress(0.5, `${mode}: preparing projection`);
        const points = await dataset.project(
          this.#projectionRequest(),
          (progress: number, stage: string) => this.#emitProgress(0.5 + progress * 0.5, stage),
        );
        if (dataset !== this.#arrowDataset) continue;
        if (revision !== this.#projectionRevision) continue;
        this.#points = points;
        this.#postData();
        this.#renderAll();
        this.#emitProgress(1, "Map ready");
        this.dispatchEvent(
          new CustomEvent("map-ready", {
            detail: { mode, binCount: Math.floor(points.length / 6) },
            bubbles: true,
            composed: true,
          }),
        );
        break;
      }
    } catch (error) {
      if (this.#arrowDataset) {
        this.dispatchEvent(
          new CustomEvent("map-error", {
            detail: error instanceof Error ? error.message : String(error),
            bubbles: true,
            composed: true,
          }),
        );
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
        colorMap: { ...this.#colorMap },
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
        zoom: this.#zoom ? { ...this.#zoom } : null,
        dataBounds: { ...bounds },
      },
    });
  }

  #localPoint(event: PointerEvent): { x: number; y: number } {
    const rect = this.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  #onPointerDown = (event: PointerEvent): void => {
    if (event.button !== 0) return;
    this.#overlay.setPointerCapture?.(event.pointerId);
    this.#dragStart = this.#localPoint(event);
    this.#dragEnd = { ...this.#dragStart };
    this.#lassoPoints = this.#interactionMode === "lasso" ? [{ ...this.#dragStart }] : [];
    this.#drawOverlay();
  };

  #onPointerMove = (event: PointerEvent): void => {
    if (!this.#dragStart) return;
    this.#dragEnd = this.#localPoint(event);
    if (this.#interactionMode === "lasso") {
      const previous = this.#lassoPoints.at(-1);
      if (
        !previous ||
        Math.hypot(this.#dragEnd.x - previous.x, this.#dragEnd.y - previous.y) >= 2
      ) {
        this.#lassoPoints.push({ ...this.#dragEnd });
      }
    } else if (this.#interactionMode === "zoomin") {
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
    this.#dragStart = null;
    this.#dragEnd = null;
    this.#lassoPoints = [];
    const transform = this.#transform();
    const [startX, startY] = this.#toData(transform, start.x, start.y);
    const [endX, endY] = this.#toData(transform, end.x, end.y);
    const dx = Math.abs(end.x - start.x);
    const dy = Math.abs(end.y - start.y);
    if (this.#interactionMode === "lasso" && lassoPoints.length >= 3) {
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
      this.#appendImmediatePoints(
        this.#projectedPoints().filter((point) => pointInPolygon(point, points)),
      );
      this.dispatchEvent(
        new CustomEvent<ScMapLassoSelection>("lasso-select", {
          detail: { points, region },
          bubbles: true,
        }),
      );
    } else if (dx >= 4 || dy >= 4) {
      const current =
        this.#zoom ??
        (() => {
          const b = this.#modeBounds();
          return { x: b.minX, y: b.minY, w: b.maxX - b.minX, h: b.maxY - b.minY };
        })();
      if (this.#interactionMode === "pan") {
        this.dispatchEvent(
          new CustomEvent("zoom-in", {
            detail: {
              x: current.x + startX - endX,
              y: current.y + startY - endY,
              w: current.w,
              h: current.h,
            },
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
        if (this.#interactionMode === "zoomin") {
          this.dispatchEvent(new CustomEvent("zoom-in", { detail: region, bubbles: true }));
        } else {
          this.#appendImmediatePoints(
            this.#projectedPoints().filter(
              ({ x, y }) =>
                x >= region.x &&
                x <= region.x + region.w &&
                y >= region.y &&
                y <= region.y + region.h,
            ),
          );
          this.dispatchEvent(new CustomEvent("box-select", { detail: region, bubbles: true }));
        }
      }
    }
    this.#drawOverlay();
  };

  #onDoubleClick = (): void => {
    this.#immediatePoints = [];
    this.dispatchEvent(
      new CustomEvent("immediate-crosshair-points", { detail: [], bubbles: true }),
    );
    this.dispatchEvent(new CustomEvent("clear-selection", { bubbles: true }));
    this.#drawOverlay();
  };

  #projectedPoints(): ScMapPoint[] {
    const result: ScMapPoint[] = [];
    const count = Math.floor(this.#points.length / 6);
    for (let index = 0; index < count; index += 1) {
      const offset = index * 6;
      result.push({ x: this.#points[offset], y: this.#points[offset + 1] });
    }
    return result;
  }

  #appendImmediatePoints(points: ScMapPoint[]): void {
    // Area selections are additive by product definition. Preserve points
    // from earlier drags until the caller explicitly clears selection.
    const immediatePointKeys = new Set(
      this.#immediatePoints.map((point) => `${point.x}:${point.y}`),
    );
    for (const point of points) {
      const key = `${point.x}:${point.y}`;
      if (immediatePointKeys.has(key)) continue;
      immediatePointKeys.add(key);
      this.#immediatePoints.push(point);
    }
    this.dispatchEvent(
      new CustomEvent("immediate-crosshair-points", {
        detail: this.#immediatePoints.map((point) => ({ ...point })),
        bubbles: true,
      }),
    );
  }
}

export function pointInPolygon(point: ScMapPoint, polygon: readonly ScMapPoint[]): boolean {
  let inside = false;
  for (
    let current = 0, previous = polygon.length - 1;
    current < polygon.length;
    previous = current++
  ) {
    const currentPoint = polygon[current];
    const previousPoint = polygon[previous];
    const edgeX = currentPoint.x - previousPoint.x;
    const edgeY = currentPoint.y - previousPoint.y;
    const pointX = point.x - previousPoint.x;
    const pointY = point.y - previousPoint.y;
    const cross = edgeX * pointY - edgeY * pointX;
    const edgeScale = Math.max(1, Math.abs(edgeX), Math.abs(edgeY));
    if (
      Math.abs(cross) <= Number.EPSILON * edgeScale * edgeScale * 8 &&
      point.x >= Math.min(previousPoint.x, currentPoint.x) &&
      point.x <= Math.max(previousPoint.x, currentPoint.x) &&
      point.y >= Math.min(previousPoint.y, currentPoint.y) &&
      point.y <= Math.max(previousPoint.y, currentPoint.y)
    ) {
      return true;
    }
    const crosses =
      currentPoint.y > point.y !== previousPoint.y > point.y &&
      point.x <
        ((previousPoint.x - currentPoint.x) * (point.y - currentPoint.y)) /
          (previousPoint.y - currentPoint.y) +
          currentPoint.x;
    if (crosses) inside = !inside;
  }
  return inside;
}

export function defineScMapElement(): void {
  if (!customElements.get(SC_MAP_TAG_NAME)) customElements.define(SC_MAP_TAG_NAME, ScMapElement);
}
