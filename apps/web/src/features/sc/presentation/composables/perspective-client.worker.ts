/// <reference lib="webworker" />

import perspective from "@perspective-dev/client";
import type { Client, Table, View } from "@perspective-dev/client";
import clientWasmUrl from "@perspective-dev/client/dist/wasm/perspective-js.wasm?url";
import type {
  PerspectiveWorkerErrorMessage,
  PerspectiveWorkerInboundMessage,
  PerspectiveWorkerRpcCall,
  PerspectiveWorkerRpcResult,
  PerspectiveWorkerViewUpdateMessage,
} from "./perspectiveWorkerProtocol";

interface WorkerGlobalWithCustomElements extends DedicatedWorkerGlobalScope {
  customElements?: {
    get: (_name: string) => undefined;
  };
}

const workerScope = self as WorkerGlobalWithCustomElements;
if (workerScope.customElements === undefined) {
  workerScope.customElements = {
    get: () => undefined,
  };
}

perspective.init_client(fetch(clientWasmUrl));

let client: Client | null = null;
let resourceSequence = 0;
const tables = new Map<string, Table>();
const views = new Map<string, View>();
const subscribedViews = new Set<string>();

function resourceId(prefix: "table" | "view"): string {
  resourceSequence += 1;
  return `${prefix}-${resourceSequence}`;
}

function requireClient(): Client {
  if (!client) throw new Error("Perspective worker client is not connected");
  return client;
}

function requireTable(id: string | undefined): Table {
  const table = id ? tables.get(id) : undefined;
  if (!table) throw new Error(`Perspective worker table "${id ?? ""}" was not found`);
  return table;
}

function requireView(id: string | undefined): View {
  const view = id ? views.get(id) : undefined;
  if (!view) throw new Error(`Perspective worker view "${id ?? ""}" was not found`);
  return view;
}

function serializeError(error: unknown): PerspectiveWorkerErrorMessage {
  if (error instanceof Error) {
    return {
      message: error.message,
      name: error.name,
      stack: error.stack,
    };
  }
  return {
    message: String(error),
    name: "Error",
  };
}

function resultTransferables(result: unknown): Transferable[] {
  if (result instanceof ArrayBuffer) return [result];
  if (ArrayBuffer.isView(result) && result.buffer instanceof ArrayBuffer) {
    return [result.buffer];
  }
  return [];
}

async function handleRpc(request: PerspectiveWorkerRpcCall): Promise<unknown> {
  const [firstArg, secondArg] = request.args;
  switch (request.method) {
    case "client.connect":
      if (client) throw new Error("Perspective worker client is already connected");
      client = await perspective.websocket(String(firstArg));
      return undefined;
    case "client.openTable": {
      const table = await requireClient().open_table(String(firstArg));
      const id = resourceId("table");
      tables.set(id, table);
      return id;
    }
    case "client.getHostedTableNames":
      return requireClient().get_hosted_table_names();
    case "table.size":
      return requireTable(request.targetId).size();
    case "table.view": {
      const view = await requireTable(request.targetId).view(firstArg as never);
      const id = resourceId("view");
      views.set(id, view);
      return id;
    }
    case "table.update":
      await requireTable(request.targetId).update(firstArg as never, secondArg as never);
      return undefined;
    case "table.makePort":
      return requireTable(request.targetId).make_port();
    case "table.delete":
      await requireTable(request.targetId).delete();
      tables.delete(request.targetId ?? "");
      return undefined;
    case "view.numRows":
      return requireView(request.targetId).num_rows();
    case "view.toColumns":
      return requireView(request.targetId).to_columns(firstArg as never);
    case "view.toJson":
      return requireView(request.targetId).to_json(firstArg as never);
    case "view.toArrow":
      return requireView(request.targetId).to_arrow(firstArg as never);
    case "view.columnPaths":
      return requireView(request.targetId).column_paths();
    case "view.subscribe": {
      const viewId = request.targetId;
      if (!viewId) throw new Error("Perspective worker view subscription is missing a view id");
      const view = requireView(viewId);
      if (!subscribedViews.has(viewId)) {
        subscribedViews.add(viewId);
        view.on_update((event: unknown) => {
          const portId = (event as { port_id?: unknown } | null)?.port_id;
          const message: PerspectiveWorkerViewUpdateMessage = {
            type: "view-update",
            viewId,
            event: typeof portId === "number" ? { port_id: portId } : {},
          };
          workerScope.postMessage(message);
        });
      }
      return undefined;
    }
    case "view.delete":
      await requireView(request.targetId).delete();
      views.delete(request.targetId ?? "");
      subscribedViews.delete(request.targetId ?? "");
      return undefined;
  }
}

workerScope.onmessage = (event: MessageEvent<PerspectiveWorkerInboundMessage>) => {
  const request = event.data;
  void handleRpc(request)
    .then((result) => {
      const response: PerspectiveWorkerRpcResult = {
        type: "response",
        id: request.id,
        ok: true,
        result,
      };
      workerScope.postMessage(response, resultTransferables(result));
    })
    .catch((error: unknown) => {
      const response: PerspectiveWorkerRpcResult = {
        type: "response",
        id: request.id,
        ok: false,
        error: serializeError(error),
      };
      workerScope.postMessage(response);
    });
};
