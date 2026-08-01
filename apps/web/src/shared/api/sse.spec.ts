import { afterEach, describe, expect, it, vi } from "vitest";
import { configureTransport } from "./client";
import { streamApiSse, streamGlobalAgentChat } from "./sse";

describe("streamApiSse", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("does not apply the ordinary request timeout to a completion stream", async () => {
    configureTransport({
      getToken: () => "test-token",
      getOrgId: () => "org-1",
      apiBase: "/api/v1",
    });
    const timeoutSpy = vi.spyOn(AbortSignal, "timeout");
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            'event: data\ndata: {"event_type":"data","payload":{"status":"completed","dataset_id":"dataset-1"}}\n\n',
            { status: 200, headers: { "Content-Type": "text/event-stream" } },
          ),
        ),
    );

    const event = await streamApiSse("/sc/import/stream", {
      method: "POST",
      body: { source_wafer_key: 1 },
    });

    expect(event?.payload).toEqual({ status: "completed", dataset_id: "dataset-1" });
    expect(timeoutSpy).not.toHaveBeenCalled();
  });

  it("does not apply the ordinary request timeout to the agent stream", async () => {
    configureTransport({
      getToken: () => "test-token",
      getOrgId: () => "org-1",
      apiBase: "/api/v1",
    });
    const timeoutSpy = vi.spyOn(AbortSignal, "timeout");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response('event: done\ndata: {"event_type":"done"}\n\n', {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        }),
      ),
    );

    const events = [];
    for await (const event of streamGlobalAgentChat({
      message: "Run a QA check",
      context: { page: "/datasets" },
    })) {
      events.push(event);
    }

    expect(events).toEqual([{ event: "done", data: '{"event_type":"done"}' }]);
    expect(timeoutSpy).not.toHaveBeenCalled();
  });
});
