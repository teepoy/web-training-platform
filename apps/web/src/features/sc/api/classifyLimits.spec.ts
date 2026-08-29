import { beforeEach, describe, expect, it, vi } from "vitest";
import { configureTransport } from "@/shared/api/client";
import { getScClassifyLimits } from "./classifyLimits";

describe("getScClassifyLimits", () => {
  beforeEach(() => {
    configureTransport({ apiBase: "/api/v1" });
    vi.restoreAllMocks();
  });

  it("reads the tracked browser row cap from the SC data provider", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ max_rows: 300_000 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(getScClassifyLimits()).resolves.toEqual({ max_rows: 300_000 });
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/sc/data/classify-limits",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });
});
