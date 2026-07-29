import { onUnmounted, ref, watch, type Ref } from "vue";
import type { Filter } from "@perspective-dev/client";
import type { ScPerspectiveTable as Table } from "../../composables/perspectiveWorkerClient";
import type { PerspectiveExpressions } from "@/features/sc/presentation/composables/perspectiveReticleExpressions";
import {
  managePerspectiveTable,
  type ManagedPerspectiveView,
} from "@/features/sc/presentation/composables/managedPerspectiveView";

export interface PerspectiveMapViewState {
  arrowData: Ref<ArrayBuffer[] | null>;
  pending: Ref<boolean>;
  error: Ref<string | null>;
  progressMessage: Ref<string>;
  progressPercent: Ref<number>;
}

const RAW_MAP_COLUMNS = ["wafer_x", "wafer_y", "die_x", "die_y", "reticle_x", "reticle_y"] as const;
const MAP_ARROW_CHUNK_ROWS = 25_000;

function transferableBuffer(value: unknown): ArrayBuffer {
  if (value instanceof ArrayBuffer) return value;
  if (ArrayBuffer.isView(value)) {
    return value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength) as ArrayBuffer;
  }
  throw new Error("Perspective to_arrow() returned a non-binary value");
}

export function usePerspectiveMapView(
  table: Ref<Table | null>,
  globalFilters: Ref<Filter[]>,
  legendCol: Ref<string>,
  reticleExpressions: Ref<PerspectiveExpressions>,
  onRecoverableError?: (reason: string, err: unknown) => void,
): PerspectiveMapViewState {
  const arrowData = ref<ArrayBuffer[] | null>(null);
  const pending = ref(false);
  const error = ref<string | null>(null);
  const progressMessage = ref("Waiting for map data");
  const progressPercent = ref(0);
  let loadSequence = 0;

  async function loadRawSnapshot(): Promise<void> {
    const sourceTable = table.value;
    const sequence = ++loadSequence;
    arrowData.value = null;

    if (!sourceTable) {
      pending.value = false;
      progressMessage.value = "Waiting for map data";
      progressPercent.value = 0;
      return;
    }

    pending.value = true;
    error.value = null;
    progressMessage.value = "Preparing filtered map data";
    progressPercent.value = 10;
    const columns = [...new Set([...RAW_MAP_COLUMNS, legendCol.value, "images"])];
    let view: ManagedPerspectiveView | null = null;
    try {
      view = await managePerspectiveTable(sourceTable).view({
        columns,
        expressions: reticleExpressions.value,
        filter: globalFilters.value.length > 0 ? globalFilters.value : undefined,
      });
      if (sequence !== loadSequence || sourceTable !== table.value) return;
      const totalRows = await view.num_rows();
      const chunks: ArrayBuffer[] = [];
      for (let startRow = 0; startRow < totalRows; startRow += MAP_ARROW_CHUNK_ROWS) {
        const endRow = Math.min(totalRows, startRow + MAP_ARROW_CHUNK_ROWS);
        progressMessage.value = `Exporting map rows ${startRow.toLocaleString()}–${endRow.toLocaleString()}`;
        progressPercent.value = 20 + Math.round((startRow / Math.max(1, totalRows)) * 45);
        chunks.push(
          transferableBuffer(
            await view.to_arrow({
              start_row: startRow,
              end_row: endRow,
            }),
          ),
        );
        if (sequence !== loadSequence || sourceTable !== table.value) return;
      }
      arrowData.value = chunks;
      progressMessage.value = "Transferring Arrow chunks to map";
      progressPercent.value = 70;
    } catch (cause) {
      if (sequence !== loadSequence) return;
      error.value = cause instanceof Error ? cause.message : String(cause);
      onRecoverableError?.("raw map snapshot failed", cause);
    } finally {
      view?.retire();
      if (sequence === loadSequence) pending.value = false;
    }
  }

  watch(
    [
      () => table.value,
      () => globalFilters.value,
      () => legendCol.value,
      () => reticleExpressions.value,
    ],
    () => {
      void loadRawSnapshot();
    },
    { immediate: true },
  );

  onUnmounted(() => {
    loadSequence += 1;
    arrowData.value = null;
  });

  return { arrowData, pending, error, progressMessage, progressPercent };
}
