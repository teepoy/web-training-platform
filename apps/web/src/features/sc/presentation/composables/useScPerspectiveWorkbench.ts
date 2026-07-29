import { onUnmounted, ref, type Ref } from "vue";
import { useTimeoutFn } from "@vueuse/core";
import perspective from "@perspective-dev/client";
import type { Client, Table } from "@perspective-dev/client";
import clientWasmUrl from "@perspective-dev/client/dist/wasm/perspective-js.wasm?url";
import { API_BASE, getAuthToken, getOrgId } from "@/shared/api/client";
import { managePerspectiveTable } from "@/features/sc/presentation/composables/managedPerspectiveView";

export type ScPerspectiveWorkbenchKind = "preview" | "reclassify";

export interface ScPerspectivePreviewOptions {
  kind: "preview";
  inspectionTime: string;
  waferKey: number;
}

export interface ScPerspectiveReclassifyOptions {
  kind: "reclassify";
  datasetId: string;
}

export type ScPerspectiveWorkbenchOptions =
  | ScPerspectivePreviewOptions
  | ScPerspectiveReclassifyOptions;

export interface ScPerspectiveWorkbenchState {
  table: Ref<Table | null>;
  connected: Ref<boolean>;
  dataReady: Ref<boolean>;
  error: Ref<string | null>;
  reconnecting: Ref<boolean>;
  reconnectFailed: Ref<boolean>;
  reconnectAttempt: Ref<number>;
  reconnectMaxAttempts: number;
  connect: (options: ScPerspectiveWorkbenchOptions) => Promise<void>;
  disconnect: () => void;
  reconnect: () => boolean;
  requestReconnect: (reason: string, err?: unknown) => boolean;
}

export interface ScPerspectiveWorkbenchRuntime {
  websocket?: (url: string) => Promise<Client>;
  tableNameFactory?: () => string;
  connectionTimeoutMs?: number;
  tableReadyTimeoutMs?: number;
  dataReadyTimeoutMs?: number;
  reconnectInitialDelayMs?: number;
  reconnectMaxDelayMs?: number;
  reconnectMaxAttempts?: number;
  clientProbeIntervalMs?: number;
  clientProbeTimeoutMs?: number;
  clientProbeFailureThreshold?: number;
  unexpectedTimeoutMs?: number;
}

const CONNECTION_TIMEOUT_MS = 5_000;
const TABLE_READY_TIMEOUT_MS = 5_000;
const TABLE_READY_RETRY_MS = 500;
const DATA_READY_POLL_MS = 500;
const DATA_READY_TIMEOUT_MS = 15_000;
const RECONNECT_INITIAL_DELAY_MS = 250;
const RECONNECT_MAX_DELAY_MS = 1_000;
const RECONNECT_MAX_ATTEMPTS = 2;
const CLIENT_PROBE_INTERVAL_MS = 15_000;
const CLIENT_PROBE_TIMEOUT_MS = 3_000;
const CLIENT_PROBE_FAILURE_THRESHOLD = 1;
const UNEXPECTED_TIMEOUT_MS = 60_000;
let perspectiveClientInitialized = false;

const WEBSOCKET_CLIENT_ERROR_PATTERNS = [
  /websocket/i,
  /web socket/i,
  /transport error/i,
  /message dropped/i,
  /connection.*closed/i,
  /closed.*connection/i,
  /failed to fetch/i,
  /networkerror/i,
];

type WorkbenchPhase = "idle" | "connecting" | "loading" | "ready" | "reconnecting";

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

function buildWsUrl(options: ScPerspectiveWorkbenchOptions, tableName: string): string {
  const params = new URLSearchParams();
  addCommonParams(params);
  params.set("table_name", tableName);

  if (options.kind === "preview") {
    return `${wsBaseUrl()}/perspective/inspections/${encodeURIComponent(options.inspectionTime)}/${encodeURIComponent(options.waferKey)}/ws?${params}`;
  }
  return `${wsBaseUrl()}/perspective/datasets/${encodeURIComponent(options.datasetId)}/ws?${params}`;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function withTimeout<T>(promise: Promise<T>, ms: number, message: string): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error(message)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => {
    if (timer !== undefined) clearTimeout(timer);
  });
}

async function openPerspectiveWebsocket(url: string): Promise<Client> {
  if (!perspectiveClientInitialized) {
    perspective.init_client(fetch(clientWasmUrl));
    perspectiveClientInitialized = true;
  }
  return perspective.websocket(url);
}

function perspectiveErrorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

function isWebSocketClientError(err: unknown): boolean {
  const message = perspectiveErrorMessage(err);
  return WEBSOCKET_CLIENT_ERROR_PATTERNS.some((pattern) => pattern.test(message));
}

function isTimeoutError(err: unknown): boolean {
  return /timed out/i.test(perspectiveErrorMessage(err));
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

async function openJoinedSamplesTable(
  client: Client,
  tableName: string,
  isCurrent: () => boolean,
  timeoutMs: number,
): Promise<Table> {
  const startedAt = Date.now();
  let lastError: unknown = null;

  while (isCurrent()) {
    const remainingMs = timeoutMs - (Date.now() - startedAt);
    if (remainingMs <= 0) break;
    try {
      return await withTimeout(
        client.open_table(tableName),
        remainingMs,
        `Perspective websocket table "${tableName}" did not open within ${timeoutMs}ms`,
      );
    } catch (err) {
      lastError = err;
      if (isWebSocketClientError(err)) break;
      if (Date.now() - startedAt >= timeoutMs) break;
      await sleep(Math.min(TABLE_READY_RETRY_MS, remainingMs));
    }
  }

  if (!isCurrent()) {
    throw new Error("Perspective connection was replaced before table became ready");
  }
  throw lastError instanceof Error
    ? lastError
    : new Error(`Perspective table "${tableName}" was not ready`);
}

export function useScPerspectiveWorkbench(
  runtime: ScPerspectiveWorkbenchRuntime = {},
): ScPerspectiveWorkbenchState {
  /*
   * Workbench owns the Perspective websocket lifecycle only:
   *
   *   connecting    websocket() is opening and its UUID-named table is being resolved.
   *   loading       the table is open, but the backend may still be materializing rows.
   *   ready         the first data-ready signal happened; client health checks may run.
   *   reconnecting  a transport/probe/watchdog failure scheduled a replacement connection.
   *
   * Important boundary: loading is not treated as unhealthy. The backend mock/prod service can
   * legitimately take time to publish rows after open_table() succeeds, so reconnect watchdogs
   * start only after _markReady(). This avoids looping reconnects while the table is still loading.
   */
  const table = ref<Table | null>(null);
  const connected = ref(false);
  const dataReady = ref(false);
  const error = ref<string | null>(null);
  const reconnecting = ref(false);
  const reconnectFailed = ref(false);
  const reconnectAttempt = ref(0);
  let client: Client | null = null;
  let connectionSeq = 0;
  let _dataReadyPollTimer: ReturnType<typeof setTimeout> | undefined;
  let _dataReadyDeadlineTimer: ReturnType<typeof setTimeout> | undefined;
  let _clientProbeTimer: ReturnType<typeof setTimeout> | undefined;
  let _clientProbeFailures = 0;
  let _reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  let _reconnectAttempts = 0;
  let _lastOptions: ScPerspectiveWorkbenchOptions | null = null;
  let _disposed = false;
  let _phase: WorkbenchPhase = "idle";
  const websocket = runtime.websocket ?? openPerspectiveWebsocket;
  const tableNameFactory = runtime.tableNameFactory ?? (() => crypto.randomUUID());
  const connectionTimeoutMs = runtime.connectionTimeoutMs ?? CONNECTION_TIMEOUT_MS;
  const tableReadyTimeoutMs = runtime.tableReadyTimeoutMs ?? TABLE_READY_TIMEOUT_MS;
  const dataReadyTimeoutMs = runtime.dataReadyTimeoutMs ?? DATA_READY_TIMEOUT_MS;
  const reconnectInitialDelayMs = runtime.reconnectInitialDelayMs ?? RECONNECT_INITIAL_DELAY_MS;
  const reconnectMaxDelayMs = runtime.reconnectMaxDelayMs ?? RECONNECT_MAX_DELAY_MS;
  const reconnectMaxAttempts = runtime.reconnectMaxAttempts ?? RECONNECT_MAX_ATTEMPTS;
  const clientProbeIntervalMs = runtime.clientProbeIntervalMs ?? CLIENT_PROBE_INTERVAL_MS;
  const clientProbeTimeoutMs = runtime.clientProbeTimeoutMs ?? CLIENT_PROBE_TIMEOUT_MS;
  const clientProbeFailureThreshold =
    runtime.clientProbeFailureThreshold ?? CLIENT_PROBE_FAILURE_THRESHOLD;
  const unexpectedTimeoutMs = runtime.unexpectedTimeoutMs ?? UNEXPECTED_TIMEOUT_MS;
  const unexpectedTimeout = useTimeoutFn(
    () => {
      requestReconnect("unexpected websocket client timeout");
    },
    unexpectedTimeoutMs,
    { immediate: false },
  );

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

  function _clearReconnectTimer(): void {
    if (_reconnectTimer !== undefined) {
      clearTimeout(_reconnectTimer);
      _reconnectTimer = undefined;
    }
  }

  function _setPhase(phase: WorkbenchPhase): void {
    _phase = phase;
    reconnecting.value = phase === "reconnecting";
  }

  function _clearClientProbeTimer(): void {
    if (_clientProbeTimer !== undefined) {
      clearTimeout(_clientProbeTimer);
      _clientProbeTimer = undefined;
    }
  }

  function _resetReadyWatchdog(): void {
    if (_disposed || _phase !== "ready" || !_lastOptions || table.value === null) return;
    unexpectedTimeout.stop();
    _clientProbeFailures = 0;
    unexpectedTimeout.start();
  }

  // Retire the current table/client through the managed table wrapper so in-flight views can
  // finish before delete()/terminate(). This does not clear _lastOptions; reconnect may reuse it.
  function _retireCurrentConnection(): void {
    _clearDataReadyTimers();
    _clearClientProbeTimer();
    unexpectedTimeout.stop();
    dataReady.value = false;
    const previousTable = table.value;
    const previousClient = client;
    table.value = null;
    client = null;
    connected.value = false;
    retirePerspectiveResources(previousTable, previousClient);
  }

  function _markReady(seq: number): void {
    if (seq !== connectionSeq || table.value === null) return;
    _setPhase("ready");
    reconnectFailed.value = false;
    _reconnectAttempts = 0;
    reconnectAttempt.value = 0;
    _clientProbeFailures = 0;
    dataReady.value = true;
    _clearDataReadyTimers();
    _resetReadyWatchdog();
    _scheduleClientProbe(seq);
  }

  // Data readiness polling runs before health checks. Timeout here means "still loading" unless
  // Perspective reports a concrete websocket/transport error.
  async function _pollDataReady(seq: number): Promise<void> {
    const tbl = table.value;
    if (!tbl || seq !== connectionSeq) return;

    let rowCount = 0;
    try {
      rowCount = await withTimeout(
        tbl.size(),
        clientProbeTimeoutMs,
        `Perspective data readiness probe timed out after ${clientProbeTimeoutMs}ms`,
      );
    } catch (err) {
      if (isTimeoutError(err)) {
        /* The backend may still be materializing the table. Do not start reconnect health checks
           until the first successful data-ready signal; just retry the readiness poll. */
        rowCount = 0;
      } else if (isWebSocketClientError(err)) {
        requestReconnect("data readiness polling failed", err);
        return;
      }
      /* Non-transport size errors can be transient while Perspective is publishing the table. */
    }

    if (seq !== connectionSeq || dataReady.value) return;

    if (rowCount > 0) {
      _markReady(seq);
      return;
    }

    _dataReadyPollTimer = setTimeout(() => {
      void _pollDataReady(seq);
    }, DATA_READY_POLL_MS);
  }

  function _scheduleClientProbe(seq: number): void {
    _clearClientProbeTimer();
    _clientProbeTimer = setTimeout(() => {
      _clientProbeTimer = undefined;
      void _runClientProbe(seq);
    }, clientProbeIntervalMs);
  }

  // Client probe runs only after _markReady(). A timeout here is unexpected because the table has
  // already answered successfully at least once, so it is treated as a reconnect-worthy failure.
  async function _runClientProbe(seq: number): Promise<void> {
    const tbl = table.value;
    if (!tbl || seq !== connectionSeq) return;

    try {
      await withTimeout(
        tbl.size(),
        clientProbeTimeoutMs,
        `Perspective websocket client probe timed out after ${clientProbeTimeoutMs}ms`,
      );
      _clientProbeFailures = 0;
      _resetReadyWatchdog();
    } catch (err) {
      if (seq !== connectionSeq) return;
      if (isTimeoutError(err)) {
        _clientProbeFailures += 1;
        if (_clientProbeFailures >= clientProbeFailureThreshold) {
          requestReconnect(
            `websocket client probe timed out ${_clientProbeFailures} consecutive times`,
          );
          return;
        }
        console.warn("[sc-perspective] websocket client probe timed out; keeping connection", {
          failures: _clientProbeFailures,
          threshold: clientProbeFailureThreshold,
        });
      }
      if (isWebSocketClientError(err)) {
        requestReconnect("websocket client probe failed", err);
        return;
      }
    }

    if (seq === connectionSeq) _scheduleClientProbe(seq);
  }

  function disconnect(): void {
    _setPhase("idle");
    _lastOptions = null;
    _reconnectAttempts = 0;
    reconnectAttempt.value = 0;
    reconnectFailed.value = false;
    _clearReconnectTimer();
    connectionSeq += 1;
    _retireCurrentConnection();
  }

  async function connect(options: ScPerspectiveWorkbenchOptions): Promise<void> {
    _lastOptions = options;
    _reconnectAttempts = 0;
    reconnectAttempt.value = 0;
    reconnectFailed.value = false;
    _setPhase("idle");
    _clearReconnectTimer();
    await _connectCurrentOptions();
  }

  async function _connectCurrentOptions(): Promise<void> {
    const options = _lastOptions;
    if (_disposed || !options) return;

    connectionSeq += 1;
    const seq = connectionSeq;
    _setPhase(_phase === "reconnecting" || _reconnectAttempts > 0 ? "reconnecting" : "connecting");
    _retireCurrentConnection();
    error.value = null;
    try {
      const tableName = tableNameFactory();
      const nextClient = await withTimeout(
        websocket(buildWsUrl(options, tableName)),
        connectionTimeoutMs,
        `Perspective websocket connection timed out after ${connectionTimeoutMs}ms`,
      );
      if (seq !== connectionSeq) {
        retirePerspectiveResources(null, nextClient);
        return;
      }
      client = nextClient;
      const openedTable = await openJoinedSamplesTable(
        nextClient,
        tableName,
        () => seq === connectionSeq,
        tableReadyTimeoutMs,
      );
      if (seq !== connectionSeq) {
        retirePerspectiveResources(openedTable, nextClient);
        return;
      }
      _phase = "loading";
      table.value = openedTable;
      connected.value = true;
      dataReady.value = false;
      _clearDataReadyTimers();
      _dataReadyDeadlineTimer = setTimeout(() => {
        if (seq === connectionSeq && !dataReady.value) {
          requestReconnect(`Perspective data did not become ready within ${dataReadyTimeoutMs}ms`);
        }
      }, dataReadyTimeoutMs);
      void _pollDataReady(seq);
    } catch (err) {
      if (seq === connectionSeq) {
        _retireCurrentConnection();
        error.value = perspectiveErrorMessage(err);
        if (isWebSocketClientError(err)) {
          _scheduleReconnect("connect failed", err);
        }
      }
    }
  }

  function _scheduleReconnect(reason: string, err?: unknown): boolean {
    if (_disposed || !_lastOptions) return false;
    if (_reconnectTimer !== undefined) return true;
    if (_reconnectAttempts >= reconnectMaxAttempts) {
      _setPhase("idle");
      reconnectFailed.value = true;
      reconnecting.value = false;
      const message = err === undefined ? reason : perspectiveErrorMessage(err);
      error.value = `${message}; reconnect failed after ${reconnectMaxAttempts} attempts. Please reconnect manually or refresh the page.`;
      console.warn("[sc-perspective] websocket reconnect failed", {
        reason,
        message,
        attempts: reconnectMaxAttempts,
      });
      return false;
    }
    _setPhase("reconnecting");
    reconnectFailed.value = false;

    const delay = Math.min(reconnectInitialDelayMs * 2 ** _reconnectAttempts, reconnectMaxDelayMs);
    _reconnectAttempts += 1;
    reconnectAttempt.value = _reconnectAttempts;
    const message = err === undefined ? reason : perspectiveErrorMessage(err);
    error.value = `${message}; reconnecting in ${delay}ms (${_reconnectAttempts}/${reconnectMaxAttempts})`;
    console.warn("[sc-perspective] websocket reconnect scheduled", {
      reason,
      message,
      delay,
      attempt: _reconnectAttempts,
    });
    _reconnectTimer = setTimeout(() => {
      _reconnectTimer = undefined;
      void _connectCurrentOptions();
    }, delay);
    return true;
  }

  function requestReconnect(reason: string, err?: unknown): boolean {
    if (err !== undefined && !isWebSocketClientError(err)) return false;
    connectionSeq += 1;
    _retireCurrentConnection();
    return _scheduleReconnect(reason, err);
  }

  function reconnect(): boolean {
    if (_disposed || !_lastOptions) return false;
    _clearReconnectTimer();
    _reconnectAttempts = 0;
    reconnectAttempt.value = 0;
    reconnectFailed.value = false;
    _setPhase("reconnecting");
    void _connectCurrentOptions();
    return true;
  }

  onUnmounted(() => {
    _disposed = true;
    disconnect();
  });

  return {
    table,
    connected,
    dataReady,
    error,
    reconnecting,
    reconnectFailed,
    reconnectAttempt,
    reconnectMaxAttempts,
    connect,
    disconnect,
    reconnect,
    requestReconnect,
  };
}
