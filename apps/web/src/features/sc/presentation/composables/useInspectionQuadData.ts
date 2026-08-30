import { onScopeDispose, watch, type ComputedRef } from "vue";
import type { ScSampleTableFilter, ScSampleTableSort } from "@/features/sc/domain/sampleTable";
import type { ScGlobalFilter } from "@/features/sc/domain/globalFilter";
import type { ScLegendSource } from "@/features/sc/domain/workbenchInteraction";
import type { ScReticleProjection } from "@/features/sc/domain/workbenchDataSource";
import { useSqlInspectionModel } from "./useSqlInspectionModel";
import { useScDataWorkbench } from "./useScDataWorkbench";

interface InspectionQuadDataOptions {
  variant: ComputedRef<"preview" | "reclassify" | undefined>;
  datasetId: ComputedRef<string | undefined>;
  collectionId: ComputedRef<string | undefined>;
  collectionRevisionId: ComputedRef<string | undefined>;
  inspectionTime: ComputedRef<string>;
  waferKey: ComputedRef<number>;
  legendGroupBy: ComputedRef<ScLegendSource | null | undefined>;
  globalFilter: ComputedRef<ScGlobalFilter>;
  mapFilter?: ComputedRef<ScGlobalFilter>;
  lookupFilter?: ComputedRef<ScGlobalFilter>;
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
    mapFilter: options.mapFilter,
    lookupFilter: options.lookupFilter,
    tableFilter: options.tableFilter,
    tableSort: options.tableSort,
    reticle: options.reticle,
    galleryRandomSamplingDefectIds: options.galleryRandomSamplingDefectIds,
    onRecoverableError: reportDataError,
  });

  const stopConnectionWatch = watch(
    [
      options.variant,
      options.datasetId,
      options.collectionId,
      options.collectionRevisionId,
      options.inspectionTime,
      options.waferKey,
    ],
    async ([variant, datasetId, collectionId, collectionRevisionId, inspectionTime, waferKey]) => {
      if (variant === "reclassify") {
        if (collectionId && collectionRevisionId) {
          await workbench.connect({
            kind: "collection",
            collectionId,
            revisionId: collectionRevisionId,
          });
          return;
        }
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
