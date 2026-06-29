import { onUnmounted, ref, type Ref } from "vue";
import perspective from "@perspective-dev/client";
import type { Client, Table } from "@perspective-dev/client";
import clientWasmUrl from "@perspective-dev/client/dist/wasm/perspective-js.wasm?url";
import { API_BASE, getAuthToken, getOrgId } from "@/shared/api/client";

export type ScPerspectiveWorkbenchKind = "preview" | "reclassify";

export interface ScPerspectivePreviewOptions {
  kind: "preview";
  inspectionTime: string;
  waferKey: number;
  reticleXDieCount?: number;
  reticleYDieCount?: number;
  reticleXDieShift?: number;
  reticleYDieShift?: number;
}

export interface ScPerspectiveReclassifyOptions {
  kind: "reclassify";
  datasetId: string;
  reticleXDieCount?: number;
  reticleYDieCount?: number;
  reticleXDieShift?: number;
  reticleYDieShift?: number;
}

export type ScPerspectiveWorkbenchOptions =
  | ScPerspectivePreviewOptions
  | ScPerspectiveReclassifyOptions;

export interface ScPerspectiveWorkbenchState {
  table: Ref<Table | null>;
  connected: Ref<boolean>;
  error: Ref<string | null>;
  connect: (options: ScPerspectiveWorkbenchOptions) => Promise<void>;
  disconnect: () => void;
}

let initialized = false;

async function initPerspectiveClient(): Promise<void> {
  if (initialized) return;
  await perspective.init_client(fetch(clientWasmUrl));
  initialized = true;
}

function addCommonParams(params: URLSearchParams): void {
  const token = getAuthToken();
  const orgId = getOrgId();
  if (token) params.set("token", token);
  if (orgId) params.set("org_id", orgId);
}

function wsBaseUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${API_BASE}/sc`;
}

function buildWsUrl(options: ScPerspectiveWorkbenchOptions): string {
  const params = new URLSearchParams();
  addCommonParams(params);
  if (options.reticleXDieCount != null)
    params.set("reticleXDieCount", String(options.reticleXDieCount));
  if (options.reticleYDieCount != null)
    params.set("reticleYDieCount", String(options.reticleYDieCount));
  if (options.reticleXDieShift != null)
    params.set("reticleXDieShift", String(options.reticleXDieShift));
  if (options.reticleYDieShift != null)
    params.set("reticleYDieShift", String(options.reticleYDieShift));

  if (options.kind === "preview") {
    return `${wsBaseUrl()}/perspective/inspections/${encodeURIComponent(options.inspectionTime)}/${encodeURIComponent(options.waferKey)}/ws?${params}`;
  }
  return `${wsBaseUrl()}/perspective/datasets/${encodeURIComponent(options.datasetId)}/ws?${params}`;
}

export function useScPerspectiveWorkbench(): ScPerspectiveWorkbenchState {
  const table = ref<Table | null>(null);
  const connected = ref(false);
  const error = ref<string | null>(null);
  let client: Client | null = null;

  function disconnect(): void {
    if (table.value) {
      try {
        table.value.delete();
      } catch {
        /* best effort */
      }
      table.value = null;
    }
    if (client) {
      try {
        client.terminate();
      } catch {
        /* best effort */
      }
      client = null;
    }
    connected.value = false;
  }

  async function connect(options: ScPerspectiveWorkbenchOptions): Promise<void> {
    disconnect();
    error.value = null;
    try {
      await initPerspectiveClient();
      client = await perspective.websocket(buildWsUrl(options));
      table.value = await client.open_table("joined_samples");
      connected.value = true;
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err);
      disconnect();
    }
  }

  onUnmounted(disconnect);

  return { table, connected, error, connect, disconnect };
}
