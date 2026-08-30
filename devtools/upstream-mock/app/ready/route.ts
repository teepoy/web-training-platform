import { errorResponse } from "@/src/server/http";
import { upstreamMockRepository } from "@/src/server/repository";

export async function GET(): Promise<Response> {
  try {
    await upstreamMockRepository.ready();
    return Response.json({ status: "ready" });
  } catch (error) {
    return errorResponse(error);
  }
}
