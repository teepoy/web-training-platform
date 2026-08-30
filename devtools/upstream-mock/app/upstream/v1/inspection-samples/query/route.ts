import { NextResponse } from "next/server";
import { z } from "zod";

import { parseBody, protectedRoute } from "@/src/server/http";
import { upstreamMockRepository } from "@/src/server/repository";

const requestSchema = z.object({
  inspection_time: z.coerce.date(),
  wafer_key: z.number().int(),
  defect_ids: z.array(z.number().int().safe()).min(1),
  projection: z.array(z.string().min(1)).min(1).optional().nullable(),
});

export async function POST(request: Request): Promise<Response> {
  return protectedRoute(request, async () => {
    const body = await parseBody(request, requestSchema);
    return NextResponse.json({
      rows: await upstreamMockRepository.listPublishedMembershipSamples(
        {
          inspection_time: body.inspection_time,
          wafer_key: body.wafer_key,
        },
        body.defect_ids,
        body.projection ?? undefined,
      ),
    });
  });
}
