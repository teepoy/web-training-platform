import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, configureTransport, isApiError, requestData, toUserMessage } from "./client";

function abortableFetch(signal: AbortSignal | null | undefined): Promise<Response> {
  return new Promise((_, reject) => {
    signal?.addEventListener(
      "abort",
      () => reject(signal.reason ?? new DOMException("Aborted", "AbortError")),
      { once: true },
    );
  });
}

describe("API transport", () => {
  const onAuthError = vi.fn();

  beforeEach(() => {
    onAuthError.mockReset();
    configureTransport({
      getToken: () => "test-token",
      getOrgId: () => "org-1",
      onAuthError,
      authEnabled: () => true,
      apiBase: "/api/v1",
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns a JSON success body directly", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ id: "dataset-1" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(requestData<{ id: string }>("/api/v1/datasets/1")).resolves.toEqual({
      id: "dataset-1",
    });
  });

  it("returns undefined for 204 and 205 responses", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(new Response(null, { status: 205 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(requestData<void>("/api/v1/empty")).resolves.toBeUndefined();
    await expect(requestData<void>("/api/v1/reset")).resolves.toBeUndefined();
  });

  it("throws a structured ApiError for JSON HTTP failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "invalid input", field: "name" }), {
          status: 422,
          headers: {
            "Content-Type": "application/json",
            "X-Request-ID": "request-123",
          },
        }),
      ),
    );

    const error = await requestData("/api/v1/fail").catch((value: unknown) => value);

    expect(error).toBeInstanceOf(ApiError);
    expect(isApiError(error)).toBe(true);
    if (!isApiError(error)) throw new Error("Expected ApiError");
    expect(error.kind).toBe("http");
    expect(error.status).toBe(422);
    expect(error.body).toEqual({ detail: "invalid input", field: "name" });
    expect(error.requestId).toBe("request-123");
    expect(toUserMessage(error, "Fallback")).toBe("Some request values are invalid.");
  });

  it("preserves a non-JSON error body without exposing it to the user", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("perspective websocket disconnected", {
          status: 500,
          headers: { "Content-Type": "text/plain" },
        }),
      ),
    );

    const error = await requestData("/api/v1/fail").catch((value: unknown) => value);

    expect(isApiError(error)).toBe(true);
    if (!isApiError(error)) throw new Error("Expected ApiError");
    expect(error.body).toBe("perspective websocket disconnected");
    expect(toUserMessage(error, "Unable to load data")).toBe("Unable to load data");
  });

  it("adds token and organization headers to concurrent requests", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) =>
      Promise.resolve(
        new Response(JSON.stringify({ url }), {
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await Promise.all([requestData("/api/v1/a"), requestData("/api/v1/b")]);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    for (const [, init] of fetchMock.mock.calls) {
      const headers = new Headers(init.headers);
      expect(headers.get("Authorization")).toBe("Bearer test-token");
      expect(headers.get("X-Organization-ID")).toBe("org-1");
    }
  });

  it("runs the auth callback for an authenticated 401 without showing UI", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 401 })));

    await expect(requestData("/api/v1/private")).rejects.toMatchObject({ status: 401 });
    expect(onAuthError).toHaveBeenCalledOnce();
  });

  it("distinguishes network failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));

    await expect(requestData("/api/v1/data")).rejects.toMatchObject({
      kind: "network",
      status: null,
    });
  });

  it("distinguishes timeout from caller cancellation", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init?: RequestInit) => abortableFetch(init?.signal)),
    );

    await expect(requestData("/api/v1/slow", {}, 5)).rejects.toMatchObject({
      kind: "timeout",
    });

    const controller = new AbortController();
    const cancelled = requestData("/api/v1/cancelled", { signal: controller.signal }, 1_000);
    controller.abort();
    await expect(cancelled).rejects.toMatchObject({ name: "AbortError" });
  });
});
