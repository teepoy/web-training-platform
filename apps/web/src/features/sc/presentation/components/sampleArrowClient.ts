import type { DecodedSampleArrowTable } from "./sampleArrowDecode";

interface PendingDecode {
  reject: (error: Error) => void;
  resolve: (result: DecodedSampleArrowTable) => void;
}

export interface SampleArrowDecoder {
  decode(data: unknown): Promise<DecodedSampleArrowTable>;
  dispose(): void;
}

function copyIpcBuffer(data: unknown): ArrayBuffer {
  if (data instanceof ArrayBuffer) return data;
  if (ArrayBuffer.isView(data)) {
    const view = data as ArrayBufferView;
    return view.buffer.slice(view.byteOffset, view.byteOffset + view.byteLength) as ArrayBuffer;
  }
  throw new TypeError("Sample table returned an unsupported Arrow IPC value");
}

export function createSampleArrowDecoder(): SampleArrowDecoder {
  if (typeof Worker === "undefined") {
    let disposed = false;
    return {
      async decode(data) {
        if (disposed) throw new Error("Sample Arrow decoder has been disposed");
        const { decodeSampleArrowIpc } = await import("./sampleArrowDecode");
        return decodeSampleArrowIpc(copyIpcBuffer(data));
      },
      dispose() {
        disposed = true;
      },
    };
  }

  const worker = new Worker(new URL("./sample-arrow.worker.ts", import.meta.url), {
    type: "module",
  });
  const pending = new Map<number, PendingDecode>();
  let requestId = 0;
  let disposed = false;

  worker.onmessage = (
    event: MessageEvent<{
      error?: string;
      id: number;
      result?: DecodedSampleArrowTable;
      type: "decoded" | "error";
    }>,
  ) => {
    const call = pending.get(event.data.id);
    if (!call) return;
    pending.delete(event.data.id);
    if (event.data.type === "error" || !event.data.result) {
      call.reject(new Error(event.data.error ?? "Sample Arrow worker failed"));
      return;
    }
    call.resolve(event.data.result);
  };

  worker.onerror = (event) => {
    const error = new Error(event.message || "Sample Arrow worker failed");
    for (const call of pending.values()) call.reject(error);
    pending.clear();
    worker.terminate();
  };

  return {
    decode(data) {
      if (disposed) return Promise.reject(new Error("Sample Arrow decoder has been disposed"));
      const ipc = copyIpcBuffer(data);
      const id = ++requestId;
      return new Promise((resolve, reject) => {
        pending.set(id, { reject, resolve });
        worker.postMessage({ id, ipc }, [ipc]);
      });
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      worker.terminate();
      const error = new Error("Sample Arrow decoder has been disposed");
      for (const call of pending.values()) call.reject(error);
      pending.clear();
    },
  };
}
