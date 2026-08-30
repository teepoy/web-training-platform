import "server-only";

import { timingSafeEqual } from "node:crypto";

import { NextResponse } from "next/server";
import { ZodError, type ZodType } from "zod";

import { upstreamMockConfig } from "./config";
import { UpstreamMockError } from "./errors";

function sameSecret(actual: string, expected: string): boolean {
  const left = Buffer.from(actual);
  const right = Buffer.from(expected);
  return left.length === right.length && timingSafeEqual(left, right);
}

export function authorize(request: Request): NextResponse | undefined {
  const expected = `Bearer ${upstreamMockConfig.apiToken()}`;
  const actual = request.headers.get("authorization") ?? "";
  if (!sameSecret(actual, expected)) {
    return NextResponse.json(
      { detail: "valid upstream mock bearer token required" },
      { status: 401 },
    );
  }
}

export async function parseBody<T>(request: Request, schema: ZodType<T>): Promise<T> {
  return schema.parse(await request.json());
}

export function errorResponse(error: unknown): NextResponse {
  if (error instanceof UpstreamMockError) {
    return NextResponse.json({ detail: error.message }, { status: error.status });
  }
  if (error instanceof ZodError) {
    return NextResponse.json(
      { detail: error.issues.map((issue) => issue.message).join("; ") },
      { status: 422 },
    );
  }
  if (error instanceof TypeError) {
    return NextResponse.json({ detail: error.message }, { status: 422 });
  }
  console.error(error);
  return NextResponse.json({ detail: "upstream mock request failed" }, { status: 500 });
}

export async function protectedRoute(
  request: Request,
  action: () => Promise<Response>,
): Promise<Response> {
  const unauthorized = authorize(request);
  if (unauthorized) return unauthorized;
  try {
    return await action();
  } catch (error) {
    return errorResponse(error);
  }
}
