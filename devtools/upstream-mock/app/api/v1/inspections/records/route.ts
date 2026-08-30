import { appendRecordsSchema } from "@/src/server/contracts";
import { parseBody, protectedRoute } from "@/src/server/http";
import { upstreamMockRepository } from "@/src/server/repository";

export async function POST(request: Request): Promise<Response> {
  return protectedRoute(request, async () => {
    const body = await parseBody(request, appendRecordsSchema);
    await upstreamMockRepository.appendRecords(body);
    return new Response(null, { status: 204 });
  });
}
