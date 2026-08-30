import { NextResponse } from "next/server";

import { protectedRoute } from "@/src/server/http";
import { upstreamMockRepository } from "@/src/server/repository";

export async function GET(
  request: Request,
  context: { params: Promise<{ waferKey: string }> },
): Promise<Response> {
  return protectedRoute(request, async () => {
    const { waferKey } = await context.params;
    const rawTime = new URL(request.url).searchParams.get("inspection_time");
    const parsedKey = Number(waferKey);
    const inspectionTime = rawTime ? new Date(rawTime) : new Date(Number.NaN);
    if (!Number.isInteger(parsedKey) || !Number.isFinite(inspectionTime.getTime())) {
      throw new TypeError("wafer key and inspection_time are required");
    }
    const result = await upstreamMockRepository.getPublishedInspection({
      wafer_key: parsedKey,
      inspection_time: inspectionTime,
    });
    return result
      ? NextResponse.json(result)
      : NextResponse.json({ detail: "inspection does not exist" }, { status: 404 });
  });
}
