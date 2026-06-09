import { beforeEach, describe, expect, it, afterEach } from "vitest";
import { ref, nextTick } from "vue";
import { http, HttpResponse } from "msw";
import { server } from "@/testing/msw/server";
import { withQuerySetup } from "@/testing/withQuerySetup";

import { useSampleLoader } from "./useSampleLoader";
import type { SampleWithLabels } from "@/generated/orval/models";

function makeSample(id: string): SampleWithLabels {
  return {
    id,
    dataset_id: "ds-1",
    image_uris: [],
    metadata: {},
    latest_annotation: null,
  } as SampleWithLabels;
}

function tick(ms = 100): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

describe("useSampleLoader", () => {
  let listSamplesCalls: any[][];
  let fetchSliceCalls: any[][];
  let listResponse: any;
  let sliceResponse: any;

  beforeEach(() => {
    listSamplesCalls = [];
    fetchSliceCalls = [];
    listResponse = { items: [], total: 0 };
    sliceResponse = { items: [], total: 0 };

    server.use(
      http.get(
        "/api/v1/datasets/:datasetId/samples-with-labels",
        ({ request, params }) => {
          const url = new URL(request.url);
          listSamplesCalls.push([
            params.datasetId,
            Number(url.searchParams.get("offset")),
            Number(url.searchParams.get("limit")),
            url.searchParams.get("label") || undefined,
            url.searchParams.get("order_by") || "id",
          ]);
          return HttpResponse.json(listResponse);
        },
      ),
      http.post(
        "/api/v1/datasets/:datasetId/query",
        async ({ request, params }) => {
          const body = (await request.json()) as any;
          fetchSliceCalls.push([params.datasetId, body.params]);
          return HttpResponse.json(sliceResponse);
        },
      ),
    );
  });

  it("uses listSamplesWithLabels when no sampleIds are provided", async () => {
    listResponse = {
      items: [makeSample("a"), makeSample("b")],
      total: 2,
    };

    const { result: loader } = withQuerySetup(() =>
      useSampleLoader({ datasetId: "ds-1", pageSize: 100 }),
    );
    await tick();

    expect(loader.samples.value.map((s) => s.id)).toEqual(["a", "b"]);
    expect(loader.totalCount.value).toBe(2);
  });

  it("uses fetchSampleSlice when sampleIds are non-empty", async () => {
    sliceResponse = {
      items: [makeSample("x"), makeSample("y")],
      total: 2,
    };

    const sampleIds = ref<string[] | null>(["x", "y"]);
    const { result: loader } = withQuerySetup(() =>
      useSampleLoader({
        datasetId: "ds-1",
        pageSize: 50,
        sampleIds,
      }),
    );
    await tick();

    expect(fetchSliceCalls).toHaveLength(1);
    expect(fetchSliceCalls[0]).toEqual([
      "ds-1",
      {
        offset: 0,
        limit: 50,
        order_by: "id",
        sample_ids: ["x", "y"],
      },
    ]);
    expect(loader.samples.value.map((s) => s.id)).toEqual(["x", "y"]);
  });

  it("treats null and empty sampleIds as the same no-scope state", async () => {
    listResponse = { items: [makeSample("a")], total: 1 };

    const sampleIds = ref<string[] | null>([]);
    const { result: loader } = withQuerySetup(() =>
      useSampleLoader({
        datasetId: "ds-1",
        pageSize: 100,
        sampleIds,
      }),
    );
    await tick();
    expect(listSamplesCalls).toHaveLength(1);

    sampleIds.value = null;
    await tick();

    expect(loader.samples.value.length).toBe(1);
    expect(loader.samples.value.map((s) => s.id)).toEqual(["a"]);
  });

  it("resets and refetches when sampleIds change", async () => {
    listResponse = {
      items: [makeSample("a"), makeSample("b")],
      total: 2,
    };

    const sampleIds = ref<string[] | null>(null);
    const { result: loader } = withQuerySetup(() =>
      useSampleLoader({
        datasetId: "ds-1",
        pageSize: 100,
        sampleIds,
      }),
    );
    await tick();

    sliceResponse = {
      items: [makeSample("z")],
      total: 1,
    };
    sampleIds.value = ["z"];
    await tick();

    expect(loader.samples.value.map((s) => s.id)).toEqual(["z"]);
    expect(loader.totalCount.value).toBe(1);
  });

  it("switches back to default pagination when sampleIds clears", async () => {
    sliceResponse = { items: [makeSample("z")], total: 1 };
    const sampleIds = ref<string[] | null>(["z"]);
    const { result: loader } = withQuerySetup(() =>
      useSampleLoader({
        datasetId: "ds-1",
        pageSize: 100,
        sampleIds,
      }),
    );
    await tick();

    listResponse = {
      items: [makeSample("a"), makeSample("b")],
      total: 2,
    };
    sampleIds.value = null;
    await tick();

    expect(loader.samples.value.map((s) => s.id)).toEqual(["a", "b"]);
  });
});
