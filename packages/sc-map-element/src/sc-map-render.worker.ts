/// <reference lib="webworker" />

import type { ScMapData, ScMapViewport } from "./types";
import { createMapRenderViewport, fitMapRegionToViewport } from "./map-projection";

const STRIDE = 6;

type Message =
  | { type: "init" }
  | ({ type: "data" } & ScMapData)
  | { type: "viewport"; viewport: ScMapViewport; viewportRevision: number };

let points = new Float32Array();
let colorMap: Record<string, string> = {};
let showImageMarkers = true;
let defectSize = 2;
let viewport: ScMapViewport | null = null;
let dataRevision = 0;
let viewportRevision = 0;

function draw(): void {
  if (!viewport) return;
  const { width, height, dpr } = viewport;
  const baseRegion = viewport.zoom
    ? viewport.zoom
    : viewport.dataBounds
      ? {
          x: viewport.dataBounds.minX,
          y: viewport.dataBounds.minY,
          w: viewport.dataBounds.maxX - viewport.dataBounds.minX || 1,
          h: viewport.dataBounds.maxY - viewport.dataBounds.minY || 1,
        }
      : {
          x: viewport.centerX - viewport.dataRangeNm / 2,
          y: viewport.centerY - viewport.dataRangeNm / 2,
          w: viewport.dataRangeNm,
          h: viewport.dataRangeNm,
        };
  const renderViewport = viewport.zoom
    ? createMapRenderViewport(baseRegion, width, height)
    : {
        visibleRegion: fitMapRegionToViewport(baseRegion, width, height),
        renderRegion: fitMapRegionToViewport(baseRegion, width, height),
        renderWidth: width,
        renderHeight: height,
        offsetX: 0,
        offsetY: 0,
      };
  const { renderRegion, renderWidth, renderHeight } = renderViewport;
  const canvas = new OffscreenCanvas(
    Math.max(1, Math.round(renderWidth * dpr)),
    Math.max(1, Math.round(renderHeight * dpr)),
  );
  const context = canvas.getContext("2d");
  if (!context) throw new Error("OffscreenCanvas 2D context is unavailable");
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  context.imageSmoothingEnabled = false;
  context.clearRect(0, 0, renderWidth, renderHeight);

  const scale = Math.min(renderWidth / renderRegion.w, renderHeight / renderRegion.h);
  const offsetX = -(renderRegion.x + renderRegion.w / 2);
  const offsetY = -(renderRegion.y + renderRegion.h / 2);
  const centerX = renderWidth / 2;
  const centerY = renderHeight / 2;
  const screenX = (x: number) => Math.round(centerX + (x + offsetX) * scale);
  const screenY = (y: number) => Math.round(centerY - (y + offsetY) * scale);
  const isRenderable = (x: number, y: number) =>
    x >= renderRegion.x &&
    x <= renderRegion.x + renderRegion.w &&
    y >= renderRegion.y &&
    y <= renderRegion.y + renderRegion.h &&
    (!viewport.dataBounds ||
      (x >= viewport.dataBounds.minX &&
        x <= viewport.dataBounds.maxX &&
        y >= viewport.dataBounds.minY &&
        y <= viewport.dataBounds.maxY));
  const count = Math.floor(points.length / STRIDE);
  let visiblePoints = 0;
  let imageMarkers = 0;

  for (let index = 0; index < count; index += 1) {
    const offset = index * STRIDE;
    const x = points[offset];
    const y = points[offset + 1];
    if (!isRenderable(x, y)) continue;
    visiblePoints += 1;
    context.fillStyle = colorMap[String(points[offset + 2])] ?? "rgb(255, 0, 0)";
    const halfDefectSize = defectSize / 2;
    context.fillRect(
      screenX(x) - halfDefectSize,
      screenY(y) - halfDefectSize,
      defectSize,
      defectSize,
    );
  }

  if (showImageMarkers) {
    const markerSize = Math.max(6, defectSize + 4);
    context.strokeStyle = "#000000";
    context.lineWidth = 1;
    for (let index = 0; index < count; index += 1) {
      const offset = index * STRIDE;
      if (points[offset + 4] === 0) continue;
      if (!isRenderable(points[offset], points[offset + 1])) continue;
      imageMarkers += 1;
      context.strokeRect(
        screenX(points[offset]) - markerSize / 2,
        screenY(points[offset + 1]) - markerSize / 2,
        markerSize,
        markerSize,
      );
    }
  }

  for (const [flagOffset, color] of [
    [3, "#000000"],
    [5, "#A855F7"],
  ] as const) {
    context.strokeStyle = color;
    context.beginPath();
    for (let index = 0; index < count; index += 1) {
      const offset = index * STRIDE;
      if (points[offset + flagOffset] === 0) continue;
      if (!isRenderable(points[offset], points[offset + 1])) continue;
      const x = screenX(points[offset]);
      const y = screenY(points[offset + 1]);
      context.moveTo(x - 3, y);
      context.lineTo(x + 3, y);
      context.moveTo(x, y - 3);
      context.lineTo(x, y + 3);
    }
    context.stroke();
  }

  const bitmap = canvas.transferToImageBitmap();
  self.postMessage(
    {
      type: "render-stats",
      dataRevision,
      viewportRevision,
      pointCount: count,
      visiblePoints,
      imageMarkers,
      firstPoint: count > 0 ? Array.from(points.slice(0, STRIDE)) : null,
      viewport,
      renderViewport,
      bitmap,
    },
    [bitmap],
  );
}

self.onmessage = (event: MessageEvent<Message>) => {
  if (event.data.type === "init") {
    return;
  }
  if (event.data.type === "data") {
    points = event.data.points;
    colorMap = event.data.colorMap;
    showImageMarkers = event.data.showImageMarkers;
    defectSize = event.data.defectSize;
    dataRevision += 1;
  } else {
    viewport = event.data.viewport;
    viewportRevision = event.data.viewportRevision;
  }
  draw();
};
