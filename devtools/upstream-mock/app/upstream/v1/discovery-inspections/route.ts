import { NextResponse } from "next/server";

import { protectedRoute } from "@/src/server/http";
import { upstreamMockRepository } from "@/src/server/repository";

function optionalTimestamp(params: URLSearchParams, name: string): Date | undefined {
  const value = params.get(name);
  if (value === null) return undefined;
  if (!/(?:Z|[+-]\d{2}:\d{2})$/.test(value)) {
    throw new TypeError(`${name} must be an ISO-8601 timestamp with a timezone`);
  }
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime())) throw new TypeError(`${name} is invalid`);
  return parsed;
}

function optionalInteger(params: URLSearchParams, name: string): number | undefined {
  const value = params.get(name);
  if (value === null) return undefined;
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed)) throw new TypeError(`${name} must be an integer`);
  return parsed;
}

export async function GET(request: Request): Promise<Response> {
  return protectedRoute(request, async () => {
    const params = new URL(request.url).searchParams;
    const order = params.get("order");
    if (order !== "primary_key" && order !== "publication") {
      throw new TypeError("order must be primary_key or publication");
    }
    const pageSize = optionalInteger(params, "page_size");
    if (pageSize === undefined || pageSize <= 0) {
      throw new TypeError("page_size must be greater than zero");
    }
    return NextResponse.json(
      await upstreamMockRepository.listDiscoveryInspections({
        order,
        pageSize,
        startTime: optionalTimestamp(params, "start_time"),
        endTime: optionalTimestamp(params, "end_time"),
        publishedFrom: optionalTimestamp(params, "published_from"),
        publishedUntil: optionalTimestamp(params, "published_until"),
        afterInspectionTime: optionalTimestamp(params, "after_inspection_time"),
        afterWaferKey: optionalInteger(params, "after_wafer_key"),
        afterPublishedAt: optionalTimestamp(params, "after_published_at"),
      }),
    );
  });
}
