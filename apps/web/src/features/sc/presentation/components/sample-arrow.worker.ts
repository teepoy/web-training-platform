/// <reference lib="webworker" />

import { decodeSampleArrowIpc } from "./sampleArrowDecode";

interface DecodeMessage {
  id: number;
  ipc: ArrayBuffer;
}

self.onmessage = (event: MessageEvent<DecodeMessage>) => {
  const { id, ipc } = event.data;
  try {
    self.postMessage({
      id,
      result: decodeSampleArrowIpc(ipc),
      type: "decoded",
    });
  } catch (error) {
    self.postMessage({
      error: error instanceof Error ? error.message : String(error),
      id,
      type: "error",
    });
  }
};
