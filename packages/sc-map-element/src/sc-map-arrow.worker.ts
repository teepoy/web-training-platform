/// <reference lib="webworker" />

import { tableFromIPC, type Table, type Vector } from "apache-arrow";
import type { ScMapRegion } from "./types";
import { encodeLegendKey, normalizeLegendKey } from "./legend-key-codec";
import { overscanMapRegion } from "./map-projection";

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

interface ResolveHighlightsMessage {
  id: number;
  type: "resolve-highlights";
  defectIds: number[];
}

type WorkerMessage = LoadMessage | ProjectMessage | ResolveHighlightsMessage;

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
    for (const name of [
      "defect_id",
      "wafer_x",
      "wafer_y",
      "die_x",
      "die_y",
      "reticle_x",
      "reticle_y",
    ]) {
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

function findDefectRow(defectIds: Vector, defectId: number): number {
  let low = 0;
  let high = defectIds.length - 1;
  while (low <= high) {
    const middle = (low + high) >>> 1;
    const current = Number(defectIds.get(middle));
    if (current === defectId) return middle;
    if (current < defectId) low = middle + 1;
    else high = middle - 1;
  }
  return -1;
}

function resolveHighlights(message: ResolveHighlightsMessage): void {
  const requestedIds = [...new Set(message.defectIds.filter(Number.isFinite))];
  const resolved = new Float64Array(requestedIds.length * 7);
  const searchableTables = tables.map((table) => ({
    defectIds: requireColumn(table, "defect_id"),
    waferX: requireColumn(table, "wafer_x"),
    waferY: requireColumn(table, "wafer_y"),
    dieX: requireColumn(table, "die_x"),
    dieY: requireColumn(table, "die_y"),
    reticleX: requireColumn(table, "reticle_x"),
    reticleY: requireColumn(table, "reticle_y"),
  }));
  let resolvedCount = 0;

  for (const defectId of requestedIds) {
    for (const table of searchableTables) {
      // The map SQL contract orders each Arrow snapshot by defect_id, allowing
      // selected coordinates to be resolved without a 300k-entry JS Map.
      const rowIndex = findDefectRow(table.defectIds, defectId);
      if (rowIndex < 0) continue;
      const offset = resolvedCount * 7;
      resolved[offset] = defectId;
      resolved[offset + 1] = Number(table.waferX.get(rowIndex));
      resolved[offset + 2] = Number(table.waferY.get(rowIndex));
      resolved[offset + 3] = Number(table.dieX.get(rowIndex));
      resolved[offset + 4] = Number(table.dieY.get(rowIndex));
      resolved[offset + 5] = Number(table.reticleX.get(rowIndex));
      resolved[offset + 6] = Number(table.reticleY.get(rowIndex));
      resolvedCount += 1;
      break;
    }
  }

  const highlights = resolved.slice(0, resolvedCount * 7);
  self.postMessage({ id: message.id, type: "highlights-resolved", highlights }, [
    highlights.buffer,
  ]);
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
  const legendCodes = new Map<string, number>();
  const legendKeys: string[] = [];
  const interval = Math.max(1, Math.floor(totalRows / 100));
  let displayRows = 0;
  let processedRows = 0;
  const projectionRegion = message.zoom ? overscanMapRegion(message.zoom) : null;

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
      if (
        projectionRegion &&
        (x < projectionRegion.x ||
          x > projectionRegion.x + projectionRegion.w ||
          y < projectionRegion.y ||
          y > projectionRegion.y + projectionRegion.h)
      ) {
        continue;
      }

      const legendKey = normalizeLegendKey(legendColumnName, legendColumn.get(rowIndex));
      if (hidden.has(legendKey)) continue;
      const legendCode = encodeLegendKey(legendKey, legendCodes, legendKeys);
      const gx = Math.floor(x / message.binSize);
      const gy = Math.floor(y / message.binSize);
      const key = `${gx}:${gy}`;
      const existingOffset = binOffsets.get(key);
      if (existingOffset !== undefined) {
        display[existingOffset + 2] = legendCode;
        if (Number(imagesColumn?.get(rowIndex) ?? 0) > 0) display[existingOffset + 4] = 1;
      } else {
        const offset = displayRows * 6;
        binOffsets.set(key, offset);
        display[offset] = gx * message.binSize + message.binSize / 2;
        display[offset + 1] = gy * message.binSize + message.binSize / 2;
        display[offset + 2] = legendCode;
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
  self.postMessage({ id: message.id, type: "projected", points, legendKeys }, [points.buffer]);
}

self.onmessage = (event: MessageEvent<WorkerMessage>) => {
  try {
    if (event.data.type === "load") load(event.data);
    else if (event.data.type === "project") project(event.data);
    else resolveHighlights(event.data);
  } catch (error) {
    self.postMessage({
      id: event.data.id,
      type: "error",
      error: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack : undefined,
    });
  }
};
