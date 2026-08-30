import { NextResponse } from "next/server";

import { protectedRoute } from "@/src/server/http";
import { upstreamMockRepository } from "@/src/server/repository";

export async function GET(
  request: Request,
  context: { params: Promise<{ waferKey: string }> },
): Promise<Response> {
  return protectedRoute(request, async () => {
    const { waferKey } = await context.params;
    const params = new URL(request.url).searchParams;
    const key = {
      wafer_key: Number(waferKey),
      inspection_time: new Date(params.get("inspection_time") ?? Number.NaN),
    };
    const offset = Number(params.get("offset") ?? "0");
    const count = Number(params.get("count") ?? "65536");
    if (
      !Number.isInteger(key.wafer_key) ||
      !Number.isFinite(key.inspection_time.getTime()) ||
      !Number.isInteger(offset) ||
      offset < 0 ||
      !Number.isInteger(count) ||
      count < 0 ||
      count > 65536
    ) {
      throw new TypeError(
        "wafer key, inspection_time, non-negative offset, and count up to 65536 are required",
      );
    }
    return NextResponse.json({
      rows: await upstreamMockRepository.listPublishedSamples(key, offset, count),
    });
  });
}
