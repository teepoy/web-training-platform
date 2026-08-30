import { NextResponse } from "next/server";

import { inspectionKeySchema } from "@/src/server/contracts";
import { parseBody, protectedRoute } from "@/src/server/http";
import { upstreamMockRepository } from "@/src/server/repository";

export async function POST(request: Request): Promise<Response> {
  return protectedRoute(request, async () => {
    const body = await parseBody(request, inspectionKeySchema);
    return NextResponse.json(await upstreamMockRepository.getInspection(body));
  });
}
