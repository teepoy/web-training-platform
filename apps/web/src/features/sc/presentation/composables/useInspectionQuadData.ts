import { onScopeDispose, watch, type ComputedRef } from "vue";
import type { ScSampleTableFilter, ScSampleTableSort } from "@/features/sc/domain/sampleTable";
import type { ScLegendSource } from "@/features/sc/domain/workbenchInteraction";
import type { ScReticleProjection } from "@/features/sc/domain/workbenchDataSource";
import { useSqlInspectionModel } from "./useSqlInspectionModel";
import { useScDataWorkbench } from "./useScDataWorkbench";

interface InspectionQuadDataOptions {
  variant: ComputedRef<"preview" | "reclassify" | undefined>;
  datasetId: ComputedRef<string | undefined>;
  inspectionTime: ComputedRef<string>;
  waferKey: ComputedRef<number>;
  legendGroupBy: ComputedRef<ScLegendSource | null | undefined>;
  globalFilter: ComputedRef<ScSampleTableFilter>;
  tableFilter: ComputedRef<ScSampleTableFilter | undefined>;
  tableSort: ComputedRef<ScSampleTableSort | null | undefined>;
  reticle: ComputedRef<ScReticleProjection>;
  galleryRandomSamplingDefectIds: ComputedRef<Set<string> | undefined>;
}

export function useInspectionQuadData(options: InspectionQuadDataOptions) {
  const workbench = useScDataWorkbench();
  const dataReady = workbench.dataReady;
  let disposed = false;

  function reportDataError(reason: string, err: unknown): void {
    if (disposed) return;
    const error = err instanceof Error ? err : new Error(String(err));
    console.error(`[sc-data-provider] ${reason}`, error);
  }

  const model = useSqlInspectionModel({
    dataSource: workbench.dataSource,
    legendGroupBy: options.legendGroupBy,
    globalFilter: options.globalFilter,
    tableFilter: options.tableFilter,
    tableSort: options.tableSort,
    reticle: options.reticle,
    galleryRandomSamplingDefectIds: options.galleryRandomSamplingDefectIds,
    onRecoverableError: reportDataError,
  });

  const stopConnectionWatch = watch(
    [options.variant, options.datasetId, options.inspectionTime, options.waferKey],
    async ([variant, datasetId, inspectionTime, waferKey]) => {
      if (variant === "reclassify") {
        if (!datasetId) return workbench.disconnect();
        await workbench.connect({ kind: "reclassify", datasetId });
        return;
      }
      if (!inspectionTime || waferKey === undefined) return workbench.disconnect();
      await workbench.connect({ kind: "preview", inspectionTime, waferKey });
    },
    { immediate: true },
  );

  onScopeDispose(() => {
    disposed = true;
    stopConnectionWatch();
  });

  return { workbench, dataReady, model, reportDataError };
}
