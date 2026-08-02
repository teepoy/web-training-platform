import { onScopeDispose, ref, shallowRef, type Ref } from "vue";
import { SqlWorkbenchDataSource } from "@/features/sc/api/sqlWorkbenchDataSource";
import type { ScWorkbenchDataSource } from "@/features/sc/domain/workbenchDataSource";

export type ScDataWorkbenchOptions =
  | { kind: "preview"; inspectionTime: string; waferKey: number }
  | { kind: "reclassify"; datasetId: string };

export interface ScDataWorkbenchState {
  dataSource: Ref<ScWorkbenchDataSource | null>;
  dataReady: Ref<boolean>;
  connect(options: ScDataWorkbenchOptions): Promise<void>;
  disconnect(): void;
}

export function useScDataWorkbench(): ScDataWorkbenchState {
  const dataSource = shallowRef<ScWorkbenchDataSource | null>(null);
  const dataReady = ref(false);

  async function connect(options: ScDataWorkbenchOptions): Promise<void> {
    const previous = dataSource.value;
    dataSource.value =
      options.kind === "preview"
        ? new SqlWorkbenchDataSource({
            kind: "inspection",
            inspectionTime: options.inspectionTime,
            waferKey: options.waferKey,
          })
        : new SqlWorkbenchDataSource({ kind: "dataset", datasetId: options.datasetId });
    previous?.close();
    dataReady.value = true;
  }

  function disconnect(): void {
    dataSource.value?.close();
    dataSource.value = null;
    dataReady.value = false;
  }

  onScopeDispose(disconnect);

  return {
    dataSource,
    dataReady,
    connect,
    disconnect,
  };
}
