import { beforeEach, describe, expect, it } from "vitest";
import { ref } from "vue";
import { http, HttpResponse } from "msw";
import { server } from "@/testing/msw/server";
import { withQuerySetup } from "@/testing/withQuerySetup";

import { usePreviewLoader } from "./usePreviewLoader";

function tick(ms = 100): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

describe("usePreviewLoader", () => {
  let previewCalls: any[][];
  let previewResponses: any[];

  beforeEach(() => {
    previewCalls = [];
    previewResponses = [];
  });

  function setupHandler() {
    server.use(
      http.get(
        "/api/v1/preview-sessions/:sessionId/items",
        ({ request, params }) => {
          const url = new URL(request.url);
          previewCalls.push([
            params.sessionId,
            url.searchParams.get("cursor") || null,
            Number(url.searchParams.get("limit")),
          ]);
          const response = previewResponses.shift() ?? {
            items: [],
            estimated_total: 0,
            has_more: false,
            next_cursor: null,
          };
          return HttpResponse.json(response);
        },
      ),
    );
  }

  it("loadMore accumulates items across pages", async () => {
    previewResponses = [
      {
        items: [{ upstream_item_id: "a", image_uris: ["/a.jpg"] }],
        estimated_total: 100,
        has_more: true,
        next_cursor: "cursor1",
      },
      {
        items: [{ upstream_item_id: "b", image_uris: ["/b.jpg"] }],
        estimated_total: 100,
        has_more: false,
        next_cursor: null,
      },
    ];
    setupHandler();

    const { result: loader } = withQuerySetup(() =>
      usePreviewLoader({ sessionId: "session1" }),
    );

    await loader.loadMore();
    expect(loader.items.value.length).toBe(1);
    expect(loader.items.value[0].upstream_item_id).toBe("a");

    await loader.loadMore();
    expect(loader.items.value.length).toBe(2);
    expect(loader.items.value[1].upstream_item_id).toBe("b");
  });

  it("loadMore deduplicates by upstream_item_id", async () => {
    previewResponses = [
      {
        items: [{ upstream_item_id: "a", image_uris: ["/a.jpg"] }],
        estimated_total: 100,
        has_more: true,
        next_cursor: "c1",
      },
      {
        items: [{ upstream_item_id: "a", image_uris: ["/a.jpg"] }],
        estimated_total: 100,
        has_more: true,
        next_cursor: "c2",
      },
    ];
    setupHandler();

    const { result: loader } = withQuerySetup(() =>
      usePreviewLoader({ sessionId: "session1" }),
    );

    await loader.loadMore();
    expect(loader.items.value.length).toBe(1);

    await loader.loadMore();
    expect(loader.items.value.length).toBe(1);
  });

  it("refetches on reset", async () => {
    previewResponses = [
      {
        items: [{ upstream_item_id: "a", image_uris: ["/a.jpg"] }],
        estimated_total: 100,
        has_more: true,
        next_cursor: "c1",
      },
      {
        items: [],
        estimated_total: 0,
        has_more: false,
        next_cursor: null,
      },
    ];
    setupHandler();

    const { result: loader } = withQuerySetup(() =>
      usePreviewLoader({ sessionId: "session1" }),
    );
    await loader.loadMore();
    expect(loader.items.value.length).toBe(1);

    loader.reset();
    await tick();

    expect(loader.items.value.length).toBe(0);
  });

  it("auto-resets when sessionId ref changes", async () => {
    previewResponses = [
      {
        items: [{ upstream_item_id: "a", image_uris: ["/a.jpg"] }],
        estimated_total: 100,
        has_more: true,
        next_cursor: "c1",
      },
      {
        items: [],
        estimated_total: 0,
        has_more: false,
        next_cursor: null,
      },
    ];
    setupHandler();

    const sessionId = ref("session1");
    const { result: loader } = withQuerySetup(() =>
      usePreviewLoader({ sessionId }),
    );

    await loader.loadMore();
    expect(loader.items.value.length).toBe(1);

    sessionId.value = "session2";
    await tick();

    expect(loader.items.value.length).toBe(0);
  });
});
