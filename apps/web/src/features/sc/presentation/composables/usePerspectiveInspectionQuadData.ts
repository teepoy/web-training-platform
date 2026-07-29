import { computed, onScopeDispose, watch, type ComputedRef } from "vue";
import type { Filter } from "@perspective-dev/client";
import type { ScSampleTableFilter, ScSampleTableSort } from "@/features/sc/domain/sampleTable";
import type { ScLegendSource } from "@/features/sc/domain/workbenchInteraction";
import { usePerspectiveInspectionModel } from "./usePerspectiveInspectionModel";
import type { ScPerspectiveTable as Table } from "./perspectiveWorkerClient";
import type { PerspectiveExpressions } from "./perspectiveReticleExpressions";
import { useScPerspectiveWorkbench } from "./useScPerspectiveWorkbench";

interface PerspectiveInspectionQuadDataOptions {
  variant: ComputedRef<"preview" | "reclassify" | undefined>;
  datasetId: ComputedRef<string | undefined>;
  inspectionTime: ComputedRef<string>;
  waferKey: ComputedRef<number>;
  legendGroupBy: ComputedRef<ScLegendSource | null | undefined>;
  globalFilter: ComputedRef<ScSampleTableFilter>;
  tableFilter: ComputedRef<ScSampleTableFilter | undefined>;
  tableSort: ComputedRef<ScSampleTableSort | null | undefined>;
  reticleExpressions: ComputedRef<PerspectiveExpressions>;
  galleryRandomSamplingDefectIds: ComputedRef<Set<string> | undefined>;
}

export function usePerspectiveInspectionQuadData(options: PerspectiveInspectionQuadDataOptions) {
  const perspective = useScPerspectiveWorkbench();
  const perspectiveReady = computed(() => perspective.dataReady.value);
  const readyPerspectiveTable = computed<Table | null>(() =>
    perspectiveReady.value ? perspective.table.value : null,
  );
  let disposed = false;

  function reportPerspectiveError(reason: string, err: unknown): void {
    if (disposed) return;
    console.warn("[sc-perspective] operation failed", { reason, err });
    perspective.requestReconnect(reason, err);
  }

  const galleryRandomSamplingFilter = computed<Filter[]>(() => {
    const ids = options.galleryRandomSamplingDefectIds.value;
    return ids && ids.size > 0 ? [["defect_id", "in", [...ids]] as Filter] : [];
  });

  const model = usePerspectiveInspectionModel({
    perspectiveTable: readyPerspectiveTable,
    legendGroupBy: options.legendGroupBy,
    globalFilter: options.globalFilter,
    tableFilter: options.tableFilter,
    tableSort: options.tableSort,
    reticleExpressions: options.reticleExpressions,
    galleryRandomSamplingFilter,
    onRecoverableError: reportPerspectiveError,
  });

  const stopConnectionWatch = watch(
    [options.variant, options.datasetId, options.inspectionTime, options.waferKey],
    async ([variant, datasetId, inspectionTime, waferKey]) => {
      if (variant === "reclassify") {
        if (!datasetId) return perspective.disconnect();
        await perspective.connect({ kind: "reclassify", datasetId });
        return;
      }
      if (!inspectionTime || waferKey === undefined) return perspective.disconnect();
      await perspective.connect({ kind: "preview", inspectionTime, waferKey });
    },
    { immediate: true },
  );

  onScopeDispose(() => {
    disposed = true;
    stopConnectionWatch();
  });

  return { perspective, perspectiveReady, model, reportPerspectiveError };
}
