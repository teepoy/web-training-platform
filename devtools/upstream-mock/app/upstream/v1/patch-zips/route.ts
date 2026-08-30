import { NextResponse } from "next/server";

import { protectedRoute } from "@/src/server/http";
import { upstreamMockRepository } from "@/src/server/repository";

export async function GET(request: Request): Promise<Response> {
  return protectedRoute(request, async () => {
    const params = new URL(request.url).searchParams;
    const inspectionTime = new Date(params.get("inspection_time") ?? Number.NaN);
    const lotId = params.get("lot_id");
    const waferId = params.get("wafer_id");
    const device = params.get("device");
    const layerId = params.get("layer_id");
    if (!Number.isFinite(inspectionTime.getTime()) || !lotId || !waferId || !device || !layerId) {
      throw new TypeError("inspection identity fields are required");
    }
    return NextResponse.json(
      await upstreamMockRepository.listPublishedPatchArchives({
        inspectionTime,
        lotId,
        waferId,
        device,
        layerId,
      }),
    );
  });
}
