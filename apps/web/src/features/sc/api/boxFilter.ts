import {
  filterInspectionBoxApiV1ScInspectionsInspectionTimeWaferKeyBoxFilterPost,
  filterScDatasetBoxApiV1ScDatasetsDatasetIdBoxFilterPost,
} from "@/generated/orval/endpoints/api";
import type { ScBoxFilterRequest, ScBoxFilterResponse } from "@/generated/orval/models";
import type { ReticleMapOptions } from "../application/reticleMapOptions";
import type { ScSampleTableFilter } from "../domain/sampleTable";

export type ScMapMode = "wafer" | "die" | "reticle";

export interface ScBoxRegion {
  x: number;
  y: number;
  w: number;
  h: number;
}

function boxFilterBody(
  mode: ScMapMode,
  region: ScBoxRegion,
  options: ReticleMapOptions,
  globalFilter?: ScSampleTableFilter,
): ScBoxFilterRequest {
  const body: ScBoxFilterRequest = {
    mode,
    x: region.x,
    y: region.y,
    width: region.w,
    height: region.h,
    reticle_x_die_count: options.xDieCount,
    reticle_y_die_count: options.yDieCount,
    reticle_x_die_shift: options.xDieShift,
    reticle_y_die_shift: options.yDieShift,
  };
  if (globalFilter && Object.keys(globalFilter).length > 0) {
    body.filter = globalFilter;
  }
  return body;
}

export async function fetchScDatasetBoxFilter(
  datasetId: string,
  mode: ScMapMode,
  region: ScBoxRegion,
  options: ReticleMapOptions,
  globalFilter?: ScSampleTableFilter,
): Promise<ScBoxFilterResponse> {
  const response = await filterScDatasetBoxApiV1ScDatasetsDatasetIdBoxFilterPost(
    datasetId,
    boxFilterBody(mode, region, options, globalFilter),
  );
  return response.data as ScBoxFilterResponse;
}

export async function fetchScInspectionBoxFilter(
  inspectionTime: string,
  waferKey: number,
  mode: ScMapMode,
  region: ScBoxRegion,
  options: ReticleMapOptions,
  globalFilter?: ScSampleTableFilter,
): Promise<ScBoxFilterResponse> {
  const response = await filterInspectionBoxApiV1ScInspectionsInspectionTimeWaferKeyBoxFilterPost(
    inspectionTime,
    waferKey,
    boxFilterBody(mode, region, options, globalFilter),
  );
  return response.data as ScBoxFilterResponse;
}
