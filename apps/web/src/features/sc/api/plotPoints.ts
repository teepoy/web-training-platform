import { fromBinary } from "@bufbuild/protobuf";
import { req } from "@/shared/api/client";
import { streamApiSse } from "@/shared/api/sse";
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

export type ScMapProgressCallback = (
  status: "warmup" | "headers" | "bytes" | "decode",
  loaded: number,
  message?: string,
  total?: number,
) => void;

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
  onProgress?: ScMapProgressCallback,
): Promise<WaferMapResponse> {
  const params = buildDatasetMapParams(options, filter, legendGroupBy);
  const response = await req<Response>(
    `/sc/datasets/${encodeURIComponent(datasetId)}/plot-points?${params.toString()}`,
    { headers: { Accept: "application/x-protobuf" } },
  );
  return readMapResponse(response, onProgress);
}

export async function warmupScPlotPoints(
  datasetId: string,
  options: ReticleMapOptions,
  filter?: ScMapFilter,
  legendGroupBy?: string,
  onProgress?: ScMapProgressCallback,
): Promise<void> {
  const params = buildDatasetMapParams(options, filter, legendGroupBy);
  await warmupMapPoints(
    `/sc/datasets/${encodeURIComponent(datasetId)}/plot-points/stream?${params.toString()}`,
    onProgress,
  );
}

function buildDatasetMapParams(
  options: ReticleMapOptions,
  filter?: ScMapFilter,
  legendGroupBy?: string,
): URLSearchParams {
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
  return params;
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
  onProgress?: ScMapProgressCallback,
): Promise<WaferMapResponse> {
  const params = buildInspectionMapParams(options, filter, legendGroupBy, extra);
  const response = await req<Response>(
    `/sc/inspections/${encodeURIComponent(inspectionTime)}/${encodeURIComponent(waferKey)}/map-points?${params.toString()}`,
    { headers: { Accept: "application/x-protobuf" } },
  );
  return readMapResponse(response, onProgress);
}

export async function warmupScInspectionMapPoints(
  inspectionTime: string,
  waferKey: number,
  options: ReticleMapOptions,
  filter?: ScMapFilter,
  legendGroupBy?: string,
  extra?: InspectionMapExtra,
  onProgress?: ScMapProgressCallback,
): Promise<void> {
  const params = buildInspectionMapParams(options, filter, legendGroupBy, extra);
  await warmupMapPoints(
    `/sc/inspections/${encodeURIComponent(inspectionTime)}/${encodeURIComponent(waferKey)}/map-points/stream?${params.toString()}`,
    onProgress,
  );
}

function buildInspectionMapParams(
  options: ReticleMapOptions,
  filter?: ScMapFilter,
  legendGroupBy?: string,
  extra?: InspectionMapExtra,
): URLSearchParams {
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
  return params;
}

async function warmupMapPoints(
  path: string,
  onProgress?: ScMapProgressCallback,
): Promise<void> {
  onProgress?.("warmup", 0, undefined, 0);
  await streamApiSse(path, {
    method: "GET",
    onEvent: (event) => {
      if (event.event_type === "progress") {
        const total = Number(event.total_count ?? event.rows ?? 0);
        const rawLoaded = Number(event.loaded_count ?? 0);
        const loaded =
          total > 0 && rawLoaded > 0 && rawLoaded <= total ? rawLoaded : 0;
        onProgress?.(
          "warmup",
          loaded,
          undefined,
          total,
        );
      } else if (event.event_type === "done") {
        const rows = Number(event.rows ?? 0);
        onProgress?.("warmup", rows, undefined, rows);
      }
    },
  });
}

async function readMapResponse(
  response: Response,
  onProgress?: ScMapProgressCallback,
): Promise<WaferMapResponse> {
  const contentLength = Number(response.headers.get("content-length") ?? 0);
  onProgress?.("headers", 0, undefined, contentLength);
  if (!response.body) {
    const bytes = new Uint8Array(await response.arrayBuffer());
    onProgress?.("bytes", bytes.byteLength, undefined, contentLength);
    const parsed = fromBinary(WaferMapResponseSchema, bytes);
    onProgress?.("decode", parsed.total, undefined, parsed.total);
    return parsed;
  }
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let loaded = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    if (value.byteLength === 0) continue;
    chunks.push(value);
    loaded += value.byteLength;
    onProgress?.("bytes", loaded, undefined, contentLength);
  }
  const bytes = new Uint8Array(loaded);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  const parsed = fromBinary(WaferMapResponseSchema, bytes);
  onProgress?.("decode", parsed.total, undefined, parsed.total);
  return parsed;
}
