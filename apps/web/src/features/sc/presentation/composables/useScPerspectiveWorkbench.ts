import { onUnmounted, ref, type Ref } from "vue";
import perspective from "@perspective-dev/client";
import type { Client, Table } from "@perspective-dev/client";
import clientWasmUrl from "@perspective-dev/client/dist/wasm/perspective-js.wasm?url";
import { API_BASE, getAuthToken, getOrgId } from "@/shared/api/client";
import {
  isRecoverablePerspectiveError,
  perspectiveErrorMessage,
} from "@/features/sc/presentation/composables/perspectiveRecovery";
import { managePerspectiveTable } from "@/features/sc/presentation/composables/managedPerspectiveView";

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
  dataReady: Ref<boolean>;
  error: Ref<string | null>;
  connect: (options: ScPerspectiveWorkbenchOptions) => Promise<void>;
  disconnect: () => void;
  recover: (reason: string, err?: unknown) => Promise<boolean>;
}

let initialized = false;
const JOINED_SAMPLES_TABLE = "joined_samples";
const TABLE_READY_TIMEOUT_MS = 60_000;
const TABLE_READY_RETRY_MS = 500;
const DATA_READY_POLL_MS = 500;
const DATA_READY_DEADLINE_MS = 60_000;
const RECOVERY_DELAY_MS = 250;

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

function retirePerspectiveResources(tbl: Table | null, wsClient: Client | null): void {
  const terminateClient = () => {
    if (wsClient) {
      try {
        wsClient.terminate();
      } catch {
        /* best effort */
      }
    }
  };

  if (!tbl) {
    terminateClient();
    return;
  }

  managePerspectiveTable(tbl).retire({ onDeleted: terminateClient });
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
  const dataReady = ref(false);
  const error = ref<string | null>(null);
  let client: Client | null = null;
  let connectionSeq = 0;
  let lastOptions: ScPerspectiveWorkbenchOptions | null = null;
  let recovering = false;
  let disposed = false;
  let _dataReadyPollTimer: ReturnType<typeof setTimeout> | undefined;
  let _dataReadyDeadlineTimer: ReturnType<typeof setTimeout> | undefined;

  function _clearDataReadyTimers(): void {
    if (_dataReadyPollTimer !== undefined) {
      clearTimeout(_dataReadyPollTimer);
      _dataReadyPollTimer = undefined;
    }
    if (_dataReadyDeadlineTimer !== undefined) {
      clearTimeout(_dataReadyDeadlineTimer);
      _dataReadyDeadlineTimer = undefined;
    }
  }

  async function _pollDataReady(seq: number): Promise<void> {
    const tbl = table.value;
    if (!tbl || seq !== connectionSeq) return;

    let rowCount = 0;
    try {
      rowCount = await managePerspectiveTable(tbl).size();
    } catch {
      /* size can fail transiently while Perspective is publishing the table; retry on next poll */
    }

    if (seq !== connectionSeq || dataReady.value) return;

    if (rowCount > 0) {
      dataReady.value = true;
      _clearDataReadyTimers();
      return;
    }

    _dataReadyPollTimer = setTimeout(() => {
      void _pollDataReady(seq);
    }, DATA_READY_POLL_MS);
  }

  function disconnect(): void {
    connectionSeq += 1;
    _clearDataReadyTimers();
    dataReady.value = false;
    const previousTable = table.value;
    const previousClient = client;
    table.value = null;
    client = null;
    connected.value = false;
    retirePerspectiveResources(previousTable, previousClient);
  }

  async function connect(options: ScPerspectiveWorkbenchOptions): Promise<void> {
    lastOptions = options;
    disconnect();
    const seq = connectionSeq;
    error.value = null;
    try {
      await initPerspectiveClient();
      const nextClient = await perspective.websocket(buildWsUrl(options));
      if (seq !== connectionSeq) {
        retirePerspectiveResources(null, nextClient);
        return;
      }
      client = nextClient;
      const openedTable = await openJoinedSamplesTable(nextClient, () => seq === connectionSeq);
      if (seq !== connectionSeq) {
        retirePerspectiveResources(openedTable, nextClient);
        return;
      }
      table.value = openedTable;
      connected.value = true;
      dataReady.value = false;
      _clearDataReadyTimers();
      _dataReadyDeadlineTimer = setTimeout(() => {
        if (seq === connectionSeq && !dataReady.value) {
          dataReady.value = true;
          _clearDataReadyTimers();
        }
      }, DATA_READY_DEADLINE_MS);
      void _pollDataReady(seq);
    } catch (err) {
      if (seq === connectionSeq) {
        error.value = err instanceof Error ? err.message : String(err);
        disconnect();
      }
    }
  }

  async function recover(reason: string, err?: unknown): Promise<boolean> {
    if (disposed || recovering || !lastOptions) return false;
    if (err !== undefined && !isRecoverablePerspectiveError(err)) return false;
    recovering = true;
    const message = err === undefined ? reason : perspectiveErrorMessage(err);
    console.warn("[sc-perspective] recovering client", { reason, message });
    try {
      disconnect();
      await sleep(RECOVERY_DELAY_MS);
      if (disposed || !lastOptions) return false;
      await connect(lastOptions);
      return true;
    } finally {
      recovering = false;
    }
  }

  onUnmounted(() => {
    disposed = true;
    disconnect();
  });

  return { table, connected, dataReady, error, connect, disconnect, recover };
}
