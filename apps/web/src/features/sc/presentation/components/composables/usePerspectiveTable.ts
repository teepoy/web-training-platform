import { onMounted, onUnmounted, ref, type Ref } from "vue";
import type { Client, Table } from "@perspective-dev/client";
import perspective from "@perspective-dev/client";
import clientWasmUrl from "@perspective-dev/client/dist/wasm/perspective-js.wasm?url";
import serverWasmUrl from "@perspective-dev/server/dist/wasm/perspective-server.wasm?url";

export type PerspectiveTableMode = "server" | "client-clone";

export interface PerspectiveTableMetrics {
  mode: PerspectiveTableMode;
  serverRssMb: number | null;
  heapBeforeCloneMb: number | null;
  heapAfterArrowMb: number | null;
  heapAfterCloneMb: number | null;
  cloneArrowMb: number | null;
  cloneDownloadMs: number | null;
  cloneBuildMs: number | null;
}

export interface PerspectiveTableState {
  samplesTable: Ref<Table | null>;
  selectionsTable: Ref<Table | null>;
  joinedTable: Ref<Table | null>;
  connected: Ref<boolean>;
  error: Ref<string | null>;
  metrics: Ref<PerspectiveTableMetrics>;
}

export interface PerspectiveTableOptions {
  mode?: PerspectiveTableMode;
  statsUrl?: string;
}

const SAMPLES_TABLE_NAME = "defect_samples";
const TOTAL_ROWS = 100_000;
const INIT_CHUNK = 50_000;

const DEFAULT_METRICS: PerspectiveTableMetrics = {
  mode: "client-clone",
  serverRssMb: null,
  heapBeforeCloneMb: null,
  heapAfterArrowMb: null,
  heapAfterCloneMb: null,
  cloneArrowMb: null,
  cloneDownloadMs: null,
  cloneBuildMs: null,
};

interface PerformanceWithMemory extends Performance {
  memory?: {
    usedJSHeapSize: number;
  };
}

function ptLog(msg: string, ...args: unknown[]) {
  console.log(`[psp-table] ${msg}`, ...args);
}

function readHeapMb(): number | null {
  const memory = (performance as PerformanceWithMemory).memory;
  if (!memory) return null;
  return Math.round(memory.usedJSHeapSize / 1024 / 1024);
}

export function usePerspectiveTable(
  wsUrl: string = "ws://localhost:9090/ws",
  options: PerspectiveTableOptions = {},
): PerspectiveTableState {
  const mode = options.mode ?? "client-clone";
  const samplesTable = ref<Table | null>(null);
  const selectionsTable = ref<Table | null>(null);
  const joinedTable = ref<Table | null>(null);
  const connected = ref(false);
  const error = ref<string | null>(null);
  const metrics = ref<PerspectiveTableMetrics>({ ...DEFAULT_METRICS, mode });
  let client: Client | null = null;
  let workerClient: Client | null = null;
  let serverSourceTable: Table | null = null;
  let pollStats: ReturnType<typeof setInterval> | null = null;

  async function pollServerStats(): Promise<void> {
    const statsUrl = options.statsUrl ?? "http://localhost:9090/api/stats";
    try {
      const resp = await fetch(statsUrl);
      const data = (await resp.json()) as { server_memory_mb?: number };
      metrics.value = { ...metrics.value, serverRssMb: data.server_memory_mb ?? null };
    } catch {
      /* best effort */
    }
  }

  onMounted(async () => {
    try {
      const t0 = performance.now();
      await perspective.init_client(fetch(clientWasmUrl));
      ptLog(`init_client done (${(performance.now() - t0).toFixed(0)}ms)`);
      perspective.init_server(fetch(serverWasmUrl));

      const t1 = performance.now();
      client = await perspective.websocket(wsUrl);
      ptLog(`websocket connected (${(performance.now() - t1).toFixed(0)}ms)`);

      const t2 = performance.now();
      const sTbl: Table = await client.open_table(SAMPLES_TABLE_NAME);
      serverSourceTable = sTbl;
      ptLog(`open_table "${SAMPLES_TABLE_NAME}" done (${(performance.now() - t2).toFixed(0)}ms)`);

      let baseTable = sTbl;
      if (mode === "client-clone") {
        metrics.value = { ...metrics.value, heapBeforeCloneMb: readHeapMb() };

        const tArrow = performance.now();
        const serverView = await sTbl.view();
        const arrowBuf = await serverView.to_arrow();
        try {
          serverView.delete();
        } catch {
          /* best effort */
        }
        const cloneDownloadMs = performance.now() - tArrow;
        metrics.value = {
          ...metrics.value,
          cloneArrowMb: Number((arrowBuf.byteLength / 1024 / 1024).toFixed(2)),
          cloneDownloadMs,
          heapAfterArrowMb: readHeapMb(),
        };
        ptLog(
          `clone: Arrow ${(arrowBuf.byteLength / 1024 / 1024).toFixed(2)} MB (${cloneDownloadMs.toFixed(0)}ms)`,
        );

        const tClone = performance.now();
        workerClient = await perspective.worker();
        baseTable = await workerClient.table(arrowBuf, { index: "defect_id" });
        const cloneBuildMs = performance.now() - tClone;
        metrics.value = {
          ...metrics.value,
          cloneBuildMs,
          heapAfterCloneMb: readHeapMb(),
        };
        ptLog(`clone: client worker table ready (${cloneBuildMs.toFixed(0)}ms)`);
      }

      const tableClient = mode === "client-clone" ? workerClient : client;
      if (!tableClient) throw new Error("Perspective client not initialized");

      const t3 = performance.now();
      const selTbl: Table = await tableClient.table(
        { defect_id: "integer", map_in_selection: "integer", table_in_selection: "integer" },
        { index: "defect_id" },
      );
      ptLog(`selections table created (${(performance.now() - t3).toFixed(0)}ms)`);

      const t4 = performance.now();
      for (let i = 1; i <= TOTAL_ROWS; i += INIT_CHUNK) {
        const end = Math.min(i + INIT_CHUNK, TOTAL_ROWS + 1);
        const ids: number[] = [];
        for (let j = i; j < end; j++) ids.push(j);
        await selTbl.update({
          defect_id: ids,
          map_in_selection: ids.map(() => 0),
          table_in_selection: ids.map(() => 0),
        });
      }
      ptLog(`selections table filled (${(performance.now() - t4).toFixed(0)}ms)`);

      const t5 = performance.now();
      const jTbl: Table = await tableClient.join(baseTable, selTbl, "defect_id", {
        join_type: "inner",
      });
      const sz = await jTbl.size();
      ptLog(`joined table ready: ${sz} rows (${(performance.now() - t5).toFixed(0)}ms)`);

      samplesTable.value = baseTable;
      selectionsTable.value = selTbl;
      joinedTable.value = jTbl;
      connected.value = true;
      ptLog(`all tables ready (${(performance.now() - t0).toFixed(0)}ms total)`);
      void pollServerStats();
      pollStats = setInterval(() => void pollServerStats(), 2000);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      ptLog("ERROR:", msg);
      error.value = msg;
    }
  });

  onUnmounted(() => {
    if (pollStats) {
      clearInterval(pollStats);
      pollStats = null;
    }
    for (const tbl of [
      joinedTable.value,
      selectionsTable.value,
      samplesTable.value,
      serverSourceTable,
    ]) {
      if (tbl) {
        try {
          tbl.delete();
        } catch {
          /* best effort */
        }
      }
    }
    samplesTable.value = null;
    selectionsTable.value = null;
    joinedTable.value = null;
    serverSourceTable = null;
    if (client) {
      try {
        client.terminate();
      } catch {
        /* best effort */
      }
      client = null;
    }
    if (workerClient) {
      try {
        workerClient.terminate();
      } catch {
        /* best effort */
      }
      workerClient = null;
    }
  });

  return { samplesTable, selectionsTable, joinedTable, connected, error, metrics };
}
