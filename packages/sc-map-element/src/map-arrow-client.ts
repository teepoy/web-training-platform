import type { ScMapRegion } from "./types";

export type MapProjectionMode = "wafer" | "die" | "reticle";

export interface MapProjectionSpec {
  mode: MapProjectionMode;
  binSize: number;
  zoom: ScMapRegion | null;
  hiddenLegendKeys: string[];
}

export interface MapArrowDataset {
  project(
    spec: MapProjectionSpec,
    onProgress?: (progress: number, stage: string) => void,
  ): Promise<Float32Array>;
  dispose(): void;
}

interface PendingCall {
  resolve: (value: Float32Array | null) => void;
  reject: (error: Error) => void;
  onProgress?: (progress: number, stage: string) => void;
}

export async function createMapArrowDataset(
  arrow: ArrayBuffer | readonly ArrayBuffer[],
  legendCol: string,
  onProgress?: (progress: number, stage: string) => void,
): Promise<MapArrowDataset> {
  onProgress?.(0, "starting Arrow map worker");
  const worker = new Worker(new URL("./sc-map-arrow.worker.ts", import.meta.url), {
    type: "module",
  });
  const pending = new Map<number, PendingCall>();
  let requestId = 0;
  let disposed = false;

  worker.onmessage = (
    event: MessageEvent<{
      id: number;
      type: "progress" | "loaded" | "projected" | "error";
      progress?: number;
      stage?: string;
      points?: Float32Array;
      rowCount?: number;
      error?: string;
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
      call.reject(new Error(event.data.error ?? "Arrow worker failed"));
      return;
    }
    if (event.data.type === "loaded") {
      console.debug(
        "[sc-map:arrow]",
        JSON.stringify({ stage: "loaded", rowCount: event.data.rowCount ?? 0 }),
      );
    } else {
      console.debug(
        "[sc-map:arrow]",
        JSON.stringify({
          stage: "projected",
          binCount: Math.floor((event.data.points?.length ?? 0) / 6),
        }),
      );
    }
    call.resolve(event.data.points ?? null);
  };
  worker.onerror = (event) => {
    const error = new Error(event.message);
    for (const call of pending.values()) call.reject(error);
    pending.clear();
    worker.terminate();
  };

  function request(
    message: Record<string, unknown>,
    transfer: Transferable[] = [],
    progress?: (value: number, stage: string) => void,
  ): Promise<Float32Array | null> {
    if (disposed) return Promise.reject(new Error("Arrow map dataset has been disposed"));
    const id = ++requestId;
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject, onProgress: progress });
      worker.postMessage({ ...message, id }, transfer);
    });
  }

  const chunks = Array.isArray(arrow) ? [...arrow] : [arrow];
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
      return result ?? new Float32Array();
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
