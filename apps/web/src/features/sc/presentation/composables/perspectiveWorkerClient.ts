import PerspectiveClientWorker from "./perspective-client.worker?worker&inline";
import type {
  PerspectiveWorkerOutboundMessage,
  PerspectiveWorkerRpcCall,
  PerspectiveWorkerRpcMethod,
} from "./perspectiveWorkerProtocol";

interface PendingRpc {
  reject: (error: Error) => void;
  resolve: (result: unknown) => void;
}

type ViewUpdateCallback = (event: unknown) => void;

export interface ScPerspectiveView {
  num_rows(): Promise<number>;
  to_columns(options?: unknown): Promise<unknown>;
  to_json(options?: unknown): Promise<unknown>;
  to_arrow(options?: unknown): Promise<ArrayBuffer>;
  column_paths(): Promise<string[]>;
  on_update(callback: ViewUpdateCallback): void;
  delete(): Promise<void>;
}

export interface ScPerspectiveTable {
  size(): Promise<number>;
  view(config?: unknown): Promise<ScPerspectiveView>;
  update(data: unknown, options?: unknown): Promise<void>;
  make_port(): Promise<number>;
  delete(): Promise<void>;
}

export interface ScPerspectiveClient {
  open_table(name: string): Promise<ScPerspectiveTable>;
  get_hosted_table_names(): Promise<string[]>;
  terminate(): void;
}

class PerspectiveWorkerTransport {
  private readonly pending = new Map<number, PendingRpc>();
  private readonly viewUpdateCallbacks = new Map<string, Set<ViewUpdateCallback>>();
  private requestSequence = 0;
  private disposed = false;

  constructor(private readonly worker: Worker) {
    worker.onmessage = (event: MessageEvent<PerspectiveWorkerOutboundMessage>) => {
      const message = event.data;
      if (message.type === "view-update") {
        for (const callback of this.viewUpdateCallbacks.get(message.viewId) ?? []) {
          callback(message.event);
        }
        return;
      }

      const call = this.pending.get(message.id);
      if (!call) return;
      this.pending.delete(message.id);
      if (!message.ok) {
        const error = new Error(message.error?.message ?? "Perspective worker RPC failed");
        error.name = message.error?.name ?? "Error";
        if (message.error?.stack) error.stack = message.error.stack;
        call.reject(error);
        return;
      }
      call.resolve(message.result);
    };

    worker.onerror = (event) => {
      this.fail(new Error(event.message || "Perspective worker failed"));
    };
    worker.onmessageerror = () => {
      this.fail(new Error("Perspective worker returned an unreadable response"));
    };
  }

  request<T>(
    method: PerspectiveWorkerRpcMethod,
    targetId?: string,
    args: unknown[] = [],
  ): Promise<T> {
    if (this.disposed) {
      return Promise.reject(new Error("Perspective worker has been disposed"));
    }
    const id = ++this.requestSequence;
    const request: PerspectiveWorkerRpcCall = {
      type: "request",
      id,
      method,
      targetId,
      args,
    };
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, {
        reject,
        resolve: (result) => resolve(result as T),
      });
      try {
        this.worker.postMessage(request);
      } catch (error) {
        this.pending.delete(id);
        reject(error instanceof Error ? error : new Error(String(error)));
      }
    });
  }

  subscribeToView(viewId: string, callback: ViewUpdateCallback): void {
    let callbacks = this.viewUpdateCallbacks.get(viewId);
    if (!callbacks) {
      callbacks = new Set();
      this.viewUpdateCallbacks.set(viewId, callbacks);
      void this.request("view.subscribe", viewId).catch((error: unknown) => {
        this.fail(error instanceof Error ? error : new Error(String(error)));
      });
    }
    callbacks.add(callback);
  }

  forgetView(viewId: string): void {
    this.viewUpdateCallbacks.delete(viewId);
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.worker.terminate();
    this.rejectPending(new Error("Perspective worker has been disposed"));
    this.viewUpdateCallbacks.clear();
  }

  terminate(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.worker.terminate();
    this.rejectPending(new Error("Perspective worker was terminated"));
    this.viewUpdateCallbacks.clear();
  }

  private fail(error: Error): void {
    if (this.disposed) return;
    this.disposed = true;
    this.worker.terminate();
    this.rejectPending(error);
    this.viewUpdateCallbacks.clear();
  }

  private rejectPending(error: Error): void {
    for (const call of this.pending.values()) call.reject(error);
    this.pending.clear();
  }
}

class RemotePerspectiveView implements ScPerspectiveView {
  private deleted = false;

  constructor(
    private readonly transport: PerspectiveWorkerTransport,
    private readonly viewId: string,
  ) {}

  num_rows(): Promise<number> {
    return this.transport.request("view.numRows", this.viewId);
  }

  to_columns(options?: unknown): Promise<unknown> {
    return this.transport.request("view.toColumns", this.viewId, [options]);
  }

  to_json(options?: unknown): Promise<unknown> {
    return this.transport.request("view.toJson", this.viewId, [options]);
  }

  to_arrow(options?: unknown): Promise<ArrayBuffer> {
    return this.transport.request("view.toArrow", this.viewId, [options]);
  }

  column_paths(): Promise<string[]> {
    return this.transport.request("view.columnPaths", this.viewId);
  }

  on_update(callback: ViewUpdateCallback): void {
    if (this.deleted) throw new Error("Perspective view has already been deleted");
    this.transport.subscribeToView(this.viewId, callback);
  }

  async delete(): Promise<void> {
    if (this.deleted) return;
    this.deleted = true;
    this.transport.forgetView(this.viewId);
    await this.transport.request("view.delete", this.viewId);
  }
}

class RemotePerspectiveTable implements ScPerspectiveTable {
  private deleted = false;

  constructor(
    private readonly transport: PerspectiveWorkerTransport,
    private readonly tableId: string,
  ) {}

  size(): Promise<number> {
    return this.transport.request("table.size", this.tableId);
  }

  async view(config?: unknown): Promise<ScPerspectiveView> {
    const viewId = await this.transport.request<string>("table.view", this.tableId, [config]);
    return new RemotePerspectiveView(this.transport, viewId);
  }

  update(data: unknown, options?: unknown): Promise<void> {
    return this.transport.request("table.update", this.tableId, [data, options]);
  }

  make_port(): Promise<number> {
    return this.transport.request("table.makePort", this.tableId);
  }

  async delete(): Promise<void> {
    if (this.deleted) return;
    this.deleted = true;
    await this.transport.request("table.delete", this.tableId);
  }
}

class RemotePerspectiveClient implements ScPerspectiveClient {
  private terminated = false;

  constructor(private readonly transport: PerspectiveWorkerTransport) {}

  async open_table(name: string): Promise<ScPerspectiveTable> {
    const tableId = await this.transport.request<string>("client.openTable", undefined, [name]);
    return new RemotePerspectiveTable(this.transport, tableId);
  }

  get_hosted_table_names(): Promise<string[]> {
    return this.transport.request("client.getHostedTableNames");
  }

  terminate(): void {
    if (this.terminated) return;
    this.terminated = true;
    this.transport.dispose();
  }
}

export async function openPerspectiveWorkerClient(
  url: string,
  timeoutMs: number,
): Promise<ScPerspectiveClient> {
  if (typeof Worker === "undefined") {
    throw new Error("Perspective data requires browser Web Worker support");
  }

  const worker = new PerspectiveClientWorker();
  const transport = new PerspectiveWorkerTransport(worker);
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    await Promise.race([
      transport.request("client.connect", undefined, [url]),
      new Promise<never>((_resolve, reject) => {
        timer = setTimeout(() => {
          reject(
            new Error(`Perspective websocket worker connection timed out after ${timeoutMs}ms`),
          );
        }, timeoutMs);
      }),
    ]);
  } catch (error) {
    transport.terminate();
    throw error;
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
  return new RemotePerspectiveClient(transport);
}
