/// <reference lib="webworker" />

import type { ScMapData, ScMapViewport } from "./types";

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
  const canvas = new OffscreenCanvas(
    Math.max(1, Math.round(width * dpr)),
    Math.max(1, Math.round(height * dpr)),
  );
  const context = canvas.getContext("2d");
  if (!context) throw new Error("OffscreenCanvas 2D context is unavailable");
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  context.imageSmoothingEnabled = false;
  context.clearRect(0, 0, width, height);

  let scale: number;
  let offsetX: number;
  let offsetY: number;
  if (viewport.zoom) {
    const z = viewport.zoom;
    scale = Math.min(width / z.w, height / z.h);
    offsetX = -(z.x + z.w / 2);
    offsetY = -(z.y + z.h / 2);
  } else if (viewport.dataBounds) {
    const bounds = viewport.dataBounds;
    scale = Math.min(
      width / (bounds.maxX - bounds.minX || 1),
      height / (bounds.maxY - bounds.minY || 1),
    );
    offsetX = -(bounds.minX + bounds.maxX) / 2;
    offsetY = -(bounds.minY + bounds.maxY) / 2;
  } else {
    scale = Math.min(width, height) / viewport.dataRangeNm;
    offsetX = -viewport.centerX;
    offsetY = -viewport.centerY;
  }

  const centerX = width / 2;
  const centerY = height / 2;
  const screenX = (x: number) => Math.round(centerX + (x + offsetX) * scale);
  const screenY = (y: number) => Math.round(centerY - (y + offsetY) * scale);
  const count = Math.floor(points.length / STRIDE);
  let visiblePoints = 0;
  let imageMarkers = 0;

  for (let index = 0; index < count; index += 1) {
    const offset = index * STRIDE;
    const x = points[offset];
    const y = points[offset + 1];
    const outsideZoom =
      viewport.zoom &&
      (x < viewport.zoom.x ||
        x > viewport.zoom.x + viewport.zoom.w ||
        y < viewport.zoom.y ||
        y > viewport.zoom.y + viewport.zoom.h);
    const outsideBounds =
      !viewport.zoom &&
      viewport.dataBounds &&
      (x < viewport.dataBounds.minX ||
        x > viewport.dataBounds.maxX ||
        y < viewport.dataBounds.minY ||
        y > viewport.dataBounds.maxY);
    if (outsideZoom || outsideBounds) {
      continue;
    }
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
