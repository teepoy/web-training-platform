import { NextResponse } from "next/server";

import { showcaseScenarioSchema } from "@/src/server/contracts";
import { parseBody, protectedRoute } from "@/src/server/http";
import { publishDevShowcase } from "@/src/server/scenarios";

export const maxDuration = 300;

export async function POST(request: Request): Promise<Response> {
  return protectedRoute(request, async () => {
    const body = await parseBody(request, showcaseScenarioSchema);
    return NextResponse.json(await publishDevShowcase(body));
  });
}
