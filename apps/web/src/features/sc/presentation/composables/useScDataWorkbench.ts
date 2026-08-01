import { onScopeDispose, ref, shallowRef, type Ref } from "vue";
import { SqlWorkbenchDataSource } from "@/features/sc/api/sqlWorkbenchDataSource";
import type { ScWorkbenchDataSource } from "@/features/sc/domain/workbenchDataSource";

export type ScDataWorkbenchOptions =
  | { kind: "preview"; inspectionTime: string; waferKey: number }
  | { kind: "reclassify"; datasetId: string };

export interface ScDataWorkbenchState {
  dataSource: Ref<ScWorkbenchDataSource | null>;
  connected: Ref<boolean>;
  dataReady: Ref<boolean>;
  error: Ref<string | null>;
  reconnecting: Ref<boolean>;
  reconnectFailed: Ref<boolean>;
  reconnectAttempt: Ref<number>;
  reconnectMaxAttempts: number;
  connect(options: ScDataWorkbenchOptions): Promise<void>;
  disconnect(): void;
  reconnect(): boolean;
  requestReconnect(reason: string, error?: unknown): boolean;
}

export function useScDataWorkbench(): ScDataWorkbenchState {
  const dataSource = shallowRef<ScWorkbenchDataSource | null>(null);
  const connected = ref(false);
  const dataReady = ref(false);
  const error = ref<string | null>(null);
  const reconnecting = ref(false);
  const reconnectFailed = ref(false);
  const reconnectAttempt = ref(0);
  const reconnectMaxAttempts = 2;
  let lastOptions: ScDataWorkbenchOptions | null = null;

  async function replaceDataSource(
    options: ScDataWorkbenchOptions,
    resetReconnectAttempts: boolean,
  ): Promise<void> {
    const previous = dataSource.value;
    lastOptions = options;
    error.value = null;
    reconnectFailed.value = false;
    dataSource.value =
      options.kind === "preview"
        ? new SqlWorkbenchDataSource({
            kind: "inspection",
            inspectionTime: options.inspectionTime,
            waferKey: options.waferKey,
          })
        : new SqlWorkbenchDataSource({ kind: "dataset", datasetId: options.datasetId });
    previous?.close();
    connected.value = true;
    dataReady.value = true;
    reconnecting.value = false;
    if (resetReconnectAttempts) reconnectAttempt.value = 0;
  }

  async function connect(options: ScDataWorkbenchOptions): Promise<void> {
    await replaceDataSource(options, true);
  }

  function disconnect(): void {
    dataSource.value?.close();
    dataSource.value = null;
    connected.value = false;
    dataReady.value = false;
    reconnecting.value = false;
  }

  function reconnect(): boolean {
    if (!lastOptions) return false;
    if (reconnectAttempt.value >= reconnectMaxAttempts) {
      reconnecting.value = false;
      reconnectFailed.value = true;
      return false;
    }
    reconnectAttempt.value += 1;
    reconnecting.value = true;
    void replaceDataSource(lastOptions, false).catch((cause: unknown) => {
      error.value = cause instanceof Error ? cause.message : String(cause);
      reconnecting.value = false;
      reconnectFailed.value = reconnectAttempt.value >= reconnectMaxAttempts;
    });
    return true;
  }

  function requestReconnect(reason: string, cause?: unknown): boolean {
    error.value = cause instanceof Error ? cause.message : reason;
    return reconnect();
  }

  onScopeDispose(disconnect);

  return {
    dataSource,
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
