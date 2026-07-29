export type PerspectiveWorkerRpcMethod =
  | "client.connect"
  | "client.openTable"
  | "client.getHostedTableNames"
  | "table.size"
  | "table.view"
  | "table.update"
  | "table.makePort"
  | "table.delete"
  | "view.numRows"
  | "view.toColumns"
  | "view.toJson"
  | "view.toArrow"
  | "view.columnPaths"
  | "view.subscribe"
  | "view.delete";

export interface PerspectiveWorkerRpcCall {
  type: "request";
  id: number;
  method: PerspectiveWorkerRpcMethod;
  targetId?: string;
  args: unknown[];
}

export type PerspectiveWorkerInboundMessage = PerspectiveWorkerRpcCall;

export interface PerspectiveWorkerErrorMessage {
  message: string;
  name: string;
  stack?: string;
}

export interface PerspectiveWorkerRpcResult {
  type: "response";
  id: number;
  ok: boolean;
  result?: unknown;
  error?: PerspectiveWorkerErrorMessage;
}

export interface PerspectiveWorkerViewUpdateMessage {
  type: "view-update";
  viewId: string;
  event: unknown;
}

export type PerspectiveWorkerOutboundMessage =
  | PerspectiveWorkerRpcResult
  | PerspectiveWorkerViewUpdateMessage;
