import { NextResponse } from "next/server";

import { protectedRoute } from "@/src/server/http";
import { upstreamMockRepository } from "@/src/server/repository";

function timestamp(params: URLSearchParams, name: string): Date {
  const value = params.get(name);
  if (!value || !/(?:Z|[+-]\d{2}:\d{2})$/.test(value)) {
    throw new TypeError(`${name} must be an ISO-8601 timestamp with a timezone`);
  }
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime())) throw new TypeError(`${name} is invalid`);
  return parsed;
}

export async function GET(request: Request): Promise<Response> {
  return protectedRoute(request, async () => {
    const params = new URL(request.url).searchParams;
    return NextResponse.json(
      await upstreamMockRepository.listPublishedInspections({
        startTime: timestamp(params, "start_time"),
        endTime: timestamp(params, "end_time"),
        lotId: params.get("lot_id") ?? undefined,
        waferId: params.get("wafer_id") ?? undefined,
        layerId: params.get("layer_id") ?? undefined,
        device: params.get("device") ?? undefined,
      }),
    );
  });
}
