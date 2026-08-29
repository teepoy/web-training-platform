import type { ScMapRegion } from "./types";
import ScMapArrowWorker from "./sc-map-arrow.worker?worker&inline";

export type MapProjectionMode = "wafer" | "die" | "reticle";

export interface MapProjectionSpec {
  mode: MapProjectionMode;
  binSize: number;
  zoom: ScMapRegion | null;
  hiddenLegendKeys: string[];
}

export interface MapResolvedHighlight {
  mapId: number;
  waferX: number;
  waferY: number;
  dieX: number;
  dieY: number;
  reticleX: number;
  reticleY: number;
}

export interface MapProjectionResult {
  points: Float32Array;
  selectionPoints: Float32Array;
  legendKeys: string[];
}

export type MapSelectionConstraint =
  | { kind: "all" }
  | { kind: "ids"; ids: readonly number[] }
  | { kind: "legend"; keys: readonly string[] }
  | { kind: "rectangle"; mode: MapProjectionMode; region: ScMapRegion }
  | {
      kind: "polygon";
      mode: MapProjectionMode;
      points: ReadonlyArray<{ x: number; y: number }>;
      region: ScMapRegion;
    };

export interface MapSelectionCommand {
  operation: "append" | "replace" | "invert" | "prune" | "clear";
  constraint?: MapSelectionConstraint;
  hiddenLegendKeys: readonly string[];
}

export interface MapSelectionResult {
  ids: Int32Array;
  points: Float32Array;
}

export interface MapArrowDataset {
  project(
    spec: MapProjectionSpec,
    onProgress?: (progress: number, stage: string) => void,
  ): Promise<MapProjectionResult>;
  updateSelection(
    command: MapSelectionCommand,
    projection: MapProjectionSpec,
  ): Promise<MapSelectionResult>;
  resolveHighlights(mapIds: readonly number[]): Promise<MapResolvedHighlight[]>;
  dispose(): void;
}

export function copyMapArrowChunksForTransfer(
  arrow: ArrayBuffer | readonly ArrayBuffer[],
): ArrayBuffer[] {
  const sourceChunks = Array.isArray(arrow) ? arrow : [arrow];
  return sourceChunks.map((chunk, index) => {
    try {
      return chunk.slice(0);
    } catch (cause) {
      const error = new Error(`Failed to copy Arrow buffer at index ${index} before transfer`);
      (error as Error & { cause?: unknown }).cause = cause;
      throw error;
    }
  });
}

interface PendingCall {
  resolve: (
    value: MapProjectionResult | MapSelectionResult | Float32Array | Float64Array | null,
  ) => void;
  reject: (error: Error) => void;
  onProgress?: (progress: number, stage: string) => void;
}

export async function createMapArrowDataset(
  arrow: ArrayBuffer | readonly ArrayBuffer[],
  legendCol: string,
  onProgress?: (progress: number, stage: string) => void,
): Promise<MapArrowDataset> {
  onProgress?.(0, "starting Arrow map worker");
  const worker = new ScMapArrowWorker();
  const pending = new Map<number, PendingCall>();
  let requestId = 0;
  let disposed = false;

  worker.onmessage = (
    event: MessageEvent<{
      id: number;
      type:
        | "progress"
        | "loaded"
        | "projected"
        | "selection-updated"
        | "highlights-resolved"
        | "error";
      progress?: number;
      stage?: string;
      points?: Float32Array;
      selectionPoints?: Float32Array;
      selectionIds?: Int32Array;
      legendKeys?: string[];
      highlights?: Float64Array;
      rowCount?: number;
      error?: string;
      stack?: string;
    }>,
  ) => {
    const call = pending.get(event.data.id);
    if (!call) return;
    if (event.data.type === "progress") {
      call.onProgress?.(event.data.progress ?? 0, event.data.stage ?? "processing Arrow");
      return;
    }
    pending.delete(event.data.id);
    if (event.data.type === "error") {
      const error = new Error(event.data.error ?? "Arrow worker failed");
      if (event.data.stack) error.stack = event.data.stack;
      call.reject(error);
      return;
    }
    if (event.data.type === "loaded") {
      console.debug(
        "[sc-map:arrow]",
        JSON.stringify({ stage: "loaded", rowCount: event.data.rowCount ?? 0 }),
      );
    } else if (event.data.type === "projected") {
      console.debug(
        "[sc-map:arrow]",
        JSON.stringify({
          stage: "projected",
          binCount: Math.floor((event.data.points?.length ?? 0) / 6),
        }),
      );
    }
    if (event.data.type === "projected") {
      call.resolve({
        points: event.data.points ?? new Float32Array(),
        selectionPoints: event.data.selectionPoints ?? new Float32Array(),
        legendKeys: event.data.legendKeys ?? [],
      });
      return;
    }
    if (event.data.type === "selection-updated") {
      call.resolve({
        ids: event.data.selectionIds ?? new Int32Array(),
        points: event.data.selectionPoints ?? new Float32Array(),
      });
      return;
    }
    call.resolve(event.data.highlights ?? null);
  };
  worker.onerror = (event) => {
    const location = event.filename ? ` (${event.filename}:${event.lineno}:${event.colno})` : "";
    const error =
      event.error instanceof Error
        ? event.error
        : new Error(`${event.message || "Arrow map worker crashed"}${location}`);
    for (const call of pending.values()) call.reject(error);
    pending.clear();
    worker.terminate();
  };

  function request(
    message: Record<string, unknown>,
    transfer: Transferable[] = [],
    progress?: (value: number, stage: string) => void,
  ): Promise<MapProjectionResult | MapSelectionResult | Float32Array | Float64Array | null> {
    if (disposed) return Promise.reject(new Error("Arrow map dataset has been disposed"));
    const id = ++requestId;
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject, onProgress: progress });
      try {
        worker.postMessage({ ...message, id }, transfer);
      } catch (cause) {
        pending.delete(id);
        const type = String(message.type ?? "unknown");
        const error = new Error(`Arrow map worker request "${type}" failed before dispatch`);
        (error as Error & { cause?: unknown }).cause = cause;
        reject(error);
      }
    });
  }

  // Arrow buffers are borrowed from application state. Transfer disposable
  // copies so restarting the worker never reuses a detached source buffer.
  const chunks = copyMapArrowChunksForTransfer(arrow);
  await request({ type: "load", chunks, legendCol }, chunks, onProgress);
  onProgress?.(1, "raw Arrow snapshot ready");

  return {
    async project(projection, progress) {
      const result = await request(
        {
          type: "project",
          mode: projection.mode,
          binSize: projection.binSize,
          zoom: projection.zoom ? { ...projection.zoom } : null,
          hiddenLegendKeys: [...projection.hiddenLegendKeys],
        },
        [],
        progress,
      );
      return result && "legendKeys" in result
        ? result
        : { points: new Float32Array(), selectionPoints: new Float32Array(), legendKeys: [] };
    },
    async updateSelection(command, projection) {
      const result = await request({
        type: "update-selection",
        command: {
          ...command,
          hiddenLegendKeys: [...command.hiddenLegendKeys],
          ...(command.constraint?.kind === "ids"
            ? { constraint: { ...command.constraint, ids: [...command.constraint.ids] } }
            : command.constraint?.kind === "legend"
              ? { constraint: { ...command.constraint, keys: [...command.constraint.keys] } }
              : command.constraint?.kind === "polygon"
                ? {
                    constraint: {
                      ...command.constraint,
                      points: command.constraint.points.map((point) => ({ ...point })),
                      region: { ...command.constraint.region },
                    },
                  }
                : command.constraint?.kind === "rectangle"
                  ? {
                      constraint: {
                        ...command.constraint,
                        region: { ...command.constraint.region },
                      },
                    }
                  : {}),
        },
        projection: {
          ...projection,
          zoom: projection.zoom ? { ...projection.zoom } : null,
          hiddenLegendKeys: [...projection.hiddenLegendKeys],
        },
      });
      return result && "ids" in result
        ? result
        : { ids: new Int32Array(), points: new Float32Array() };
    },
    async resolveHighlights(mapIds) {
      if (mapIds.length === 0) return [];
      const result = await request({
        type: "resolve-highlights",
        mapIds: [...mapIds],
      });
      if (!(result instanceof Float64Array)) return [];
      const highlights: MapResolvedHighlight[] = [];
      for (let offset = 0; offset < result.length; offset += 7) {
        highlights.push({
          mapId: result[offset],
          waferX: result[offset + 1],
          waferY: result[offset + 2],
          dieX: result[offset + 3],
          dieY: result[offset + 4],
          reticleX: result[offset + 5],
          reticleY: result[offset + 6],
        });
      }
      return highlights;
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      worker.terminate();
      const error = new Error("Arrow map dataset has been disposed");
      for (const call of pending.values()) call.reject(error);
      pending.clear();
    },
  };
}
