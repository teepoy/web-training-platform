import { fromBinary } from "@bufbuild/protobuf";
import { req } from "@/shared/api/client";
import {
  WaferMapResponseSchema,
  type WaferMapResponse,
} from "../generated/proto/sc/v1/sample_pb";
import type { ReticleMapOptions } from "../application/reticleMapOptions";

export interface ScMapFilter {
  class_numbers?: number[];
  rough_bins?: number[];
  predictions?: string[];
  annotations?: string[];
  test_ids?: number[];
  adders?: number[];
  cluster_ids?: number[];
}

export function appendScMapFilterParams(
  params: URLSearchParams,
  filter?: ScMapFilter,
): void {
  if (!filter) return;
  for (const [key, values] of Object.entries(filter)) {
    if (values && values.length > 0) {
      for (const value of values) {
        params.append(key, String(value));
      }
    }
  }
}

export async function fetchScPlotPoints(
  datasetId: string,
  options: ReticleMapOptions,
  filter?: ScMapFilter,
  legendGroupBy?: string,
): Promise<WaferMapResponse> {
  const params = new URLSearchParams({
    sampled: "true",
    targetResolution: "600",
    reticleXDieCount: String(options.xDieCount),
    reticleYDieCount: String(options.yDieCount),
    reticleXDieShift: String(options.xDieShift),
    reticleYDieShift: String(options.yDieShift),
  });
  appendScMapFilterParams(params, filter);
  if (legendGroupBy) {
    params.set("legend_group_by", legendGroupBy);
  }
  const response = await req<Response>(
    `/sc/datasets/${encodeURIComponent(datasetId)}/plot-points?${params.toString()}`,
    { headers: { Accept: "application/x-protobuf" } },
  );
  return fromBinary(
    WaferMapResponseSchema,
    new Uint8Array(await response.arrayBuffer()),
  );
}

export interface InspectionMapExtra {
  mode?: "wafer" | "die" | "reticle";
  sampled?: boolean;
  gridSizeNm?: number;
  zoom?: { x: number; y: number; w: number; h: number } | null;
}

export async function fetchScInspectionMapPoints(
  inspectionTime: string,
  waferKey: number,
  options: ReticleMapOptions,
  filter?: ScMapFilter,
  legendGroupBy?: string,
  extra?: InspectionMapExtra,
): Promise<WaferMapResponse> {
  const params = new URLSearchParams({
    sampled: extra?.sampled !== undefined ? String(extra.sampled) : "true",
    gridSizeNm: String(extra?.gridSizeNm ?? 600),
    reticleXDieCount: String(options.xDieCount),
    reticleYDieCount: String(options.yDieCount),
    reticleXDieShift: String(options.xDieShift),
    reticleYDieShift: String(options.yDieShift),
  });
  if (extra?.mode) {
    params.set("mode", extra.mode);
  }
  if (extra?.zoom) {
    params.set("zoomX", String(Math.round(extra.zoom.x)));
    params.set("zoomY", String(Math.round(extra.zoom.y)));
    params.set("zoomW", String(Math.round(extra.zoom.w)));
    params.set("zoomH", String(Math.round(extra.zoom.h)));
  }
  appendScMapFilterParams(params, filter);
  if (legendGroupBy) {
    params.set("legend_group_by", legendGroupBy);
  }
  const response = await req<Response>(
    `/sc/inspections/${encodeURIComponent(inspectionTime)}/${encodeURIComponent(waferKey)}/map-points?${params.toString()}`,
    { headers: { Accept: "application/x-protobuf" } },
  );
  return fromBinary(
    WaferMapResponseSchema,
    new Uint8Array(await response.arrayBuffer()),
  );
}
