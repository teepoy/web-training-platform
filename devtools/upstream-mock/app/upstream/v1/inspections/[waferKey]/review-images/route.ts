import { NextResponse } from "next/server";

import { protectedRoute } from "@/src/server/http";
import { upstreamMockRepository } from "@/src/server/repository";

export async function GET(
  request: Request,
  context: { params: Promise<{ waferKey: string }> },
): Promise<Response> {
  return protectedRoute(request, async () => {
    const { waferKey } = await context.params;
    const key = {
      wafer_key: Number(waferKey),
      inspection_time: new Date(
        new URL(request.url).searchParams.get("inspection_time") ?? Number.NaN,
      ),
    };
    if (!Number.isInteger(key.wafer_key) || !Number.isFinite(key.inspection_time.getTime())) {
      throw new TypeError("wafer key and inspection_time are required");
    }
    return NextResponse.json(await upstreamMockRepository.listPublishedReviewImages(key));
  });
}
