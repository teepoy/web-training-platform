import { NextResponse } from "next/server";

import { createInspectionSchema } from "@/src/server/contracts";
import { parseBody, protectedRoute } from "@/src/server/http";
import { upstreamMockRepository } from "@/src/server/repository";

export async function POST(request: Request): Promise<Response> {
  return protectedRoute(request, async () => {
    const body = await parseBody(request, createInspectionSchema);
    return NextResponse.json(await upstreamMockRepository.createDraft(body), {
      status: 201,
    });
  });
}

export async function GET(request: Request): Promise<Response> {
  return protectedRoute(request, async () => {
    const rawState = new URL(request.url).searchParams.get("state");
    if (rawState !== null && rawState !== "draft" && rawState !== "published") {
      throw new TypeError("state must be draft or published");
    }
    return NextResponse.json(await upstreamMockRepository.listInspections(rawState ?? undefined));
  });
}

export async function PATCH(request: Request): Promise<Response> {
  return protectedRoute(request, async () => {
    const { updateInspectionSchema } = await import("@/src/server/contracts");
    const body = await parseBody(request, updateInspectionSchema);
    return NextResponse.json(await upstreamMockRepository.updatePublished(body));
  });
}
