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
const JOINED_SAMPLES_TABLE = "joined_samples";
const TABLE_READY_TIMEOUT_MS = 60_000;
const TABLE_READY_RETRY_MS = 500;

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

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function openJoinedSamplesTable(client: Client, isCurrent: () => boolean): Promise<Table> {
  const startedAt = Date.now();
  let lastError: unknown = null;

  while (isCurrent()) {
    try {
      return await client.open_table(JOINED_SAMPLES_TABLE);
    } catch (err) {
      lastError = err;
      if (Date.now() - startedAt >= TABLE_READY_TIMEOUT_MS) break;
      await sleep(TABLE_READY_RETRY_MS);
    }
  }

  if (!isCurrent()) {
    throw new Error("Perspective connection was replaced before table became ready");
  }
  throw lastError instanceof Error
    ? lastError
    : new Error(`Perspective table "${JOINED_SAMPLES_TABLE}" was not ready`);
}

export function useScPerspectiveWorkbench(): ScPerspectiveWorkbenchState {
  const table = ref<Table | null>(null);
  const connected = ref(false);
  const error = ref<string | null>(null);
  let client: Client | null = null;
  let connectionSeq = 0;

  function disconnect(): void {
    connectionSeq += 1;
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
    const seq = connectionSeq;
    error.value = null;
    try {
      await initPerspectiveClient();
      const nextClient = await perspective.websocket(buildWsUrl(options));
      if (seq !== connectionSeq) {
        nextClient.terminate();
        return;
      }
      client = nextClient;
      const openedTable = await openJoinedSamplesTable(nextClient, () => seq === connectionSeq);
      if (seq !== connectionSeq) {
        try {
          openedTable.delete();
        } catch {
          /* best effort */
        }
        return;
      }
      table.value = openedTable;
      connected.value = true;
    } catch (err) {
      if (seq === connectionSeq) {
        error.value = err instanceof Error ? err.message : String(err);
        disconnect();
      }
    }
  }

  onUnmounted(disconnect);

  return { table, connected, error, connect, disconnect };
}
