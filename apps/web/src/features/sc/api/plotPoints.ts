import { fromBinary } from "@bufbuild/protobuf";
import { req } from "@/shared/api/client";
import {
  WaferMapResponseSchema,
  type WaferMapResponse,
} from "../generated/proto/sc/v1/sample_pb";
import type { ReticleMapOptions } from "../application/reticleMapOptions";

export async function fetchScPlotPoints(
  datasetId: string,
  options: ReticleMapOptions,
): Promise<WaferMapResponse> {
  const params = new URLSearchParams({
    sampled: "true",
    targetResolution: "600",
    reticleXDieCount: String(options.xDieCount),
    reticleYDieCount: String(options.yDieCount),
    reticleXDieShift: String(options.xDieShift),
    reticleYDieShift: String(options.yDieShift),
  });
  const response = await req<Response>(
    `/sc/datasets/${encodeURIComponent(datasetId)}/plot-points?${params.toString()}`,
    { headers: { Accept: "application/x-protobuf" } },
  );
  return fromBinary(
    WaferMapResponseSchema,
    new Uint8Array(await response.arrayBuffer()),
  );
}
