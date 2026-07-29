import { tableFromArrays, tableToIPC } from "apache-arrow";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createSampleArrowDecoder } from "./sampleArrowClient";

class FakeWorker {
  static instances: FakeWorker[] = [];

  onerror: ((event: ErrorEvent) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  readonly postMessage = vi.fn();
  readonly terminate = vi.fn();

  constructor() {
    FakeWorker.instances.push(this);
  }
}

describe("sample Arrow decoder", () => {
  afterEach(() => {
    FakeWorker.instances = [];
    vi.unstubAllGlobals();
  });

  it("transfers Perspective Arrow IPC to a browser worker", async () => {
    vi.stubGlobal("Worker", FakeWorker);
    const decoder = createSampleArrowDecoder();
    const worker = FakeWorker.instances[0];
    const ipc = tableToIPC(tableFromArrays({ defect_id: [1, 2] }));

    const decodedPromise = decoder.decode(ipc);

    expect(worker?.postMessage).toHaveBeenCalledTimes(1);
    const [message, transfer] = worker?.postMessage.mock.calls[0] ?? [];
    expect(message).toMatchObject({ id: 1 });
    expect(message.ipc).toBeInstanceOf(ArrayBuffer);
    expect(transfer).toEqual([message.ipc]);

    worker?.onmessage?.(
      new MessageEvent("message", {
        data: {
          id: 1,
          result: { columns: { defect_id: [1, 2] }, numRows: 2 },
          type: "decoded",
        },
      }),
    );

    await expect(decodedPromise).resolves.toEqual({
      columns: { defect_id: [1, 2] },
      numRows: 2,
    });
    decoder.dispose();
    expect(worker?.terminate).toHaveBeenCalledOnce();
  });
});
