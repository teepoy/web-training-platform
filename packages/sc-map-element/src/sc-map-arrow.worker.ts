/// <reference lib="webworker" />

import { tableFromIPC, type Table, type Vector } from "apache-arrow";
import type { ScMapRegion } from "./types";

type MapMode = "wafer" | "die" | "reticle";

interface LoadMessage {
  id: number;
  type: "load";
  chunks: ArrayBuffer[];
  legendCol: string;
}

interface ProjectMessage {
  id: number;
  type: "project";
  mode: MapMode;
  binSize: number;
  zoom: ScMapRegion | null;
  hiddenLegendKeys: string[];
}

type WorkerMessage = LoadMessage | ProjectMessage;

const COORDINATE_COLUMNS: Record<MapMode, readonly [string, string]> = {
  wafer: ["wafer_x", "wafer_y"],
  die: ["die_x", "die_y"],
  reticle: ["reticle_x", "reticle_y"],
};

let tables: Table[] = [];
let legendColumnName = "class_number";

function progress(id: number, value: number, stage: string): void {
  self.postMessage({ id, type: "progress", progress: value, stage });
}

function requireColumn(source: Table, name: string): Vector {
  const column = source.getChild(name);
  if (column) return column;
  const available = source.schema.fields.map((field) => field.name).join(", ");
  throw new Error(`Arrow map column "${name}" is missing; available: ${available}`);
}

function load(message: LoadMessage): void {
  legendColumnName = message.legendCol;
  tables = message.chunks.map((chunk, index) => {
    progress(
      message.id,
      (index + 1) / Math.max(1, message.chunks.length),
      `decoding Arrow chunk ${index + 1}/${message.chunks.length}`,
    );
    const decoded = tableFromIPC(new Uint8Array(chunk));
    for (const name of ["wafer_x", "wafer_y", "die_x", "die_y", "reticle_x", "reticle_y"]) {
      requireColumn(decoded, name);
    }
    requireColumn(decoded, message.legendCol);
    return decoded;
  });
  const rowCount = tables.reduce((sum, table) => sum + table.numRows, 0);
  if (tables.length === 0) {
    progress(message.id, 1, "retained 0 Arrow rows");
  }
  self.postMessage({ id: message.id, type: "loaded", rowCount });
}

function project(message: ProjectMessage): void {
  if (!(message.binSize > 0) || !Number.isFinite(message.binSize)) {
    throw new Error(`Invalid map bin size: ${message.binSize}`);
  }

  const [xName, yName] = COORDINATE_COLUMNS[message.mode];
  const hidden = new Set(message.hiddenLegendKeys);
  const totalRows = tables.reduce((sum, table) => sum + table.numRows, 0);
  const display = new Float32Array(totalRows * 6);
  const binOffsets = new Map<string, number>();
  const interval = Math.max(1, Math.floor(totalRows / 100));
  let displayRows = 0;
  let processedRows = 0;

  for (const table of tables) {
    const xColumn = requireColumn(table, xName);
    const yColumn = requireColumn(table, yName);
    const legendColumn = requireColumn(table, legendColumnName);
    const imagesColumn = table.getChild("images");

    for (let rowIndex = 0; rowIndex < table.numRows; rowIndex += 1) {
      processedRows += 1;
      const x = Number(xColumn.get(rowIndex));
      const y = Number(yColumn.get(rowIndex));
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
      const zoom = message.zoom;
      if (zoom && (x < zoom.x || x > zoom.x + zoom.w || y < zoom.y || y > zoom.y + zoom.h)) {
        continue;
      }

      const legend = legendColumn.get(rowIndex);
      if (hidden.has(String(legend))) continue;
      const gx = Math.floor(x / message.binSize);
      const gy = Math.floor(y / message.binSize);
      const key = `${gx}:${gy}`;
      const existingOffset = binOffsets.get(key);
      if (existingOffset !== undefined) {
        display[existingOffset + 2] = Number(legend ?? 0);
        if (Number(imagesColumn?.get(rowIndex) ?? 0) > 0) display[existingOffset + 4] = 1;
      } else {
        const offset = displayRows * 6;
        binOffsets.set(key, offset);
        display[offset] = gx * message.binSize + message.binSize / 2;
        display[offset + 1] = gy * message.binSize + message.binSize / 2;
        display[offset + 2] = Number(legend ?? 0);
        display[offset + 4] = Number(imagesColumn?.get(rowIndex) ?? 0) > 0 ? 1 : 0;
        displayRows += 1;
      }

      if (processedRows % interval === 0) {
        progress(
          message.id,
          processedRows / Math.max(1, totalRows),
          `${message.mode}: binning ${processedRows.toLocaleString()}/${totalRows.toLocaleString()} rows`,
        );
      }
    }
  }

  const points = display.slice(0, displayRows * 6);
  progress(message.id, 1, `${message.mode}: ${displayRows.toLocaleString()} occupied bins`);
  self.postMessage({ id: message.id, type: "projected", points }, [points.buffer]);
}

self.onmessage = (event: MessageEvent<WorkerMessage>) => {
  try {
    if (event.data.type === "load") load(event.data);
    else project(event.data);
  } catch (error) {
    self.postMessage({
      id: event.data.id,
      type: "error",
      error: error instanceof Error ? error.message : String(error),
    });
  }
};
