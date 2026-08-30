import { NextResponse } from "next/server";

import { publishInspectionSchema } from "@/src/server/contracts";
import { parseBody, protectedRoute } from "@/src/server/http";
import { upstreamMockRepository } from "@/src/server/repository";

export async function POST(request: Request): Promise<Response> {
  return protectedRoute(request, async () => {
    const body = await parseBody(request, publishInspectionSchema);
    return NextResponse.json(
      await upstreamMockRepository.publish(
        {
          wafer_key: body.wafer_key,
          inspection_time: body.inspection_time,
        },
        body.published_at,
      ),
    );
  });
}
