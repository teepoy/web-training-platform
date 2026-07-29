import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  PerspectiveWorkerInboundMessage,
  PerspectiveWorkerOutboundMessage,
} from "../perspectiveWorkerProtocol";
import { openPerspectiveWorkerClient } from "../perspectiveWorkerClient";

class FakeWorker {
  static instances: FakeWorker[] = [];

  onerror: ((event: ErrorEvent) => void) | null = null;
  onmessage: ((event: MessageEvent<PerspectiveWorkerOutboundMessage>) => void) | null = null;
  onmessageerror: ((event: MessageEvent) => void) | null = null;
  readonly postMessage = vi.fn<(message: PerspectiveWorkerInboundMessage) => void>();
  readonly terminate = vi.fn();

  constructor() {
    FakeWorker.instances.push(this);
  }

  respond(id: number, result?: unknown): void {
    this.onmessage?.(
      new MessageEvent("message", {
        data: { type: "response", id, ok: true, result } satisfies PerspectiveWorkerOutboundMessage,
      }),
    );
  }

  emitViewUpdate(viewId: string, event: unknown): void {
    this.onmessage?.(
      new MessageEvent("message", {
        data: {
          type: "view-update",
          viewId,
          event,
        } satisfies PerspectiveWorkerOutboundMessage,
      }),
    );
  }
}

function rpcRequest(worker: FakeWorker, index: number) {
  return worker.postMessage.mock.calls[index]?.[0];
}

describe("Perspective worker RPC client", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    FakeWorker.instances = [];
  });

  it("keeps client, table, and view operations behind worker RPC", async () => {
    vi.stubGlobal("Worker", FakeWorker);

    const clientPromise = openPerspectiveWorkerClient("ws://example.test/perspective", 1_000);
    const worker = FakeWorker.instances[0];
    expect(rpcRequest(worker, 0)).toMatchObject({
      type: "request",
      id: 1,
      method: "client.connect",
      args: ["ws://example.test/perspective"],
    });
    worker?.respond(1);
    const client = await clientPromise;

    const tablePromise = client.open_table("samples");
    expect(rpcRequest(worker, 1)).toMatchObject({
      id: 2,
      method: "client.openTable",
      args: ["samples"],
    });
    worker?.respond(2, "table-1");
    const table = await tablePromise;

    const viewPromise = table.view({ columns: ["defect_id"] });
    expect(rpcRequest(worker, 2)).toMatchObject({
      id: 3,
      method: "table.view",
      targetId: "table-1",
      args: [{ columns: ["defect_id"] }],
    });
    worker?.respond(3, "view-2");
    const view = await viewPromise;

    const portPromise = table.make_port();
    expect(rpcRequest(worker, 3)).toMatchObject({
      id: 4,
      method: "table.makePort",
      targetId: "table-1",
    });
    worker?.respond(4, 7);
    await expect(portPromise).resolves.toBe(7);

    const updatePromise = table.update([{ defect_id: 1, selected: true }], { port_id: 7 });
    expect(rpcRequest(worker, 4)).toMatchObject({
      id: 5,
      method: "table.update",
      targetId: "table-1",
      args: [[{ defect_id: 1, selected: true }], { port_id: 7 }],
    });
    worker?.respond(5);
    await updatePromise;

    const update = vi.fn();
    view.on_update(update);
    expect(rpcRequest(worker, 5)).toMatchObject({
      id: 6,
      method: "view.subscribe",
      targetId: "view-2",
    });
    worker?.respond(6);
    worker?.emitViewUpdate("view-2", { port_id: 7 });
    expect(update).toHaveBeenCalledWith({ port_id: 7 });

    const arrowPromise = view.to_arrow({ start_row: 0, end_row: 10 });
    expect(rpcRequest(worker, 6)).toMatchObject({
      id: 7,
      method: "view.toArrow",
      targetId: "view-2",
    });
    const arrow = new ArrayBuffer(8);
    worker?.respond(7, arrow);
    await expect(arrowPromise).resolves.toBe(arrow);

    client.terminate();
    expect(worker?.terminate).toHaveBeenCalledOnce();
  });

  it("terminates a worker whose connection exceeds the explicit timeout", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("Worker", FakeWorker);

    const clientPromise = openPerspectiveWorkerClient("ws://example.test/perspective", 25);
    const worker = FakeWorker.instances[0];
    const rejection = expect(clientPromise).rejects.toThrow(
      "Perspective websocket worker connection timed out after 25ms",
    );

    await vi.advanceTimersByTimeAsync(25);
    await rejection;
    expect(worker?.terminate).toHaveBeenCalledOnce();
  });
});
