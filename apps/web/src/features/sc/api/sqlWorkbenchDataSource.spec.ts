import { tableFromArrays, tableToIPC } from "apache-arrow";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "@/testing/msw/server";
import { createDefaultScSamplingProgram } from "@/features/sc/domain/samplingRules";
import {
  compileScSamplingSelection,
  compileScWhere,
  SqlWorkbenchDataSource,
} from "./sqlWorkbenchDataSource";

const QUERY_URL = "/api/v1/sc/data/datasets/ds-1/query";
const DESCRIPTOR_URL = "/api/v1/sc/data/sample-table-descriptor";

const sampleTableDescriptor = {
  version: "sc.sample-table.v1",
  columns: [
    {
      key: "defect_id",
      title: "Defect ID",
      width: 130,
      filter: "set",
      visibility: "default",
      format: "integer",
    },
    {
      key: "row_key",
      title: "Sample ID",
      width: 260,
      filter: "set",
      visibility: "default",
      format: "plain",
    },
  ],
};

class FakeEventSource {
  static instance: FakeEventSource | null = null;
  private readonly listeners = new Map<string, (event: MessageEvent<string>) => void>();
  closed = false;

  constructor(readonly url: string) {
    FakeEventSource.instance = this;
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
    this.listeners.set(type, listener as (event: MessageEvent<string>) => void);
  }

  close(): void {
    this.closed = true;
    this.listeners.clear();
  }

  emit(type: string, data: string): void {
    this.listeners.get(type)?.(new MessageEvent(type, { data }));
  }
}

function arrowResponse(
  columns: Parameters<typeof tableFromArrays>[0],
  revision: number,
): HttpResponse {
  return HttpResponse.arrayBuffer(tableToIPC(tableFromArrays(columns)), {
    headers: {
      "Content-Type": "application/vnd.apache.arrow.stream",
      "X-SC-Data-Revision": String(revision),
    },
  });
}

describe("SQL workbench data source", () => {
  const sources: SqlWorkbenchDataSource[] = [];

  beforeEach(() => {
    server.use(http.get(DESCRIPTOR_URL, () => HttpResponse.json(sampleTableDescriptor)));
  });

  afterEach(() => {
    for (const source of sources) source.close();
    sources.length = 0;
    FakeEventSource.instance = null;
    vi.unstubAllGlobals();
  });

  it("compiles filters to parameterized SQL and rejects unknown columns", () => {
    expect(
      compileScWhere([
        ["rough_bin", "in", [1, 2]],
        ["defect_id", "not in", [8, 9]],
        ["prediction_label", "contains", "scratch"],
        ["annotation_label", "is null", null],
        ["final_class", "in or null", ["Scratch"]],
        ["prediction_label", "not in or null", ["Particle"]],
        ["annotation_label", "not in and not null", ["Clean"]],
      ]),
    ).toEqual({
      sql: ' WHERE "rough_bin" = ANY(?) AND NOT ("defect_id" = ANY(?)) AND CONTAINS(CAST("prediction_label" AS VARCHAR), ?) AND "annotation_label" IS NULL AND ("final_class" = ANY(?) OR "final_class" IS NULL) AND (NOT ("prediction_label" = ANY(?)) OR "prediction_label" IS NULL) AND (NOT ("annotation_label" = ANY(?)) AND "annotation_label" IS NOT NULL)',
      parameters: [[1, 2], [8, 9], "scratch", ["Scratch"], ["Particle"], ["Clean"]],
    });

    expect(() => compileScWhere([["secret_path", "==", "/etc/passwd"]])).toThrow(
      "Unsupported SC data field",
    );
  });

  it("preserves nested AND and OR groups and parameter order", () => {
    expect(
      compileScWhere([
        {
          combinator: "and",
          items: [
            {
              combinator: "or",
              items: [
                ["class_number", "==", 2],
                ["class_number", "==", 3],
              ],
            },
            {
              combinator: "and",
              items: [
                ["area", ">=", 10],
                ["area", "<=", 20],
              ],
            },
          ],
        },
      ]),
    ).toEqual({
      sql: ' WHERE (("class_number" = ? OR "class_number" = ?) AND ("area" >= ? AND "area" <= ?))',
      parameters: [2, 3, 10, 20],
    });
  });

  it("sends SQL and parameters and decodes Arrow aggregates", async () => {
    let requestBody: unknown;
    server.use(
      http.post(QUERY_URL, async ({ request }) => {
        requestBody = await request.json();
        return arrowResponse({ group_key: [10, 20], group_count: [2, 3] }, 4);
      }),
    );
    const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId: "ds-1" });
    sources.push(source);

    await expect(
      source.loadAggregates({ field: "rough_bin", filters: [["class_number", "==", 7]] }),
    ).resolves.toEqual({ "10": 2, "20": 3 });
    expect(requestBody).toEqual({
      description: "sc-workbench.aggregate.rough_bin",
      sql: 'SELECT "rough_bin" AS "group_key", COUNT(*) AS "group_count" FROM samples WHERE "class_number" = ? GROUP BY "rough_bin" ORDER BY "rough_bin"',
      parameters: [7],
    });
  });

  it("queries and subscribes to one immutable collection revision", async () => {
    const collectionQueryUrl =
      "/api/v1/sc/data/collections/collection-1/revisions/revision-2/query";
    server.use(
      http.post(collectionQueryUrl, () => arrowResponse({ group_key: [10], group_count: [4] }, 3)),
    );
    vi.stubGlobal("EventSource", FakeEventSource);
    const source = new SqlWorkbenchDataSource({
      kind: "collection",
      collectionId: "collection-1",
      revisionId: "revision-2",
    });
    sources.push(source);

    await expect(source.loadAggregates({ field: "rough_bin" })).resolves.toEqual({ "10": 4 });
    source.subscribeInvalidations(() => undefined);

    expect(source.scopeKey).toBe("collection:collection-1/revision-2");
    expect(FakeEventSource.instance?.url).toContain(
      "/api/v1/sc/data/collections/collection-1/revisions/revision-2/events",
    );
  });

  it("does not refresh for an unchanged SSE baseline and closes without listeners", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId: "ds-1" });
    sources.push(source);
    const listener = vi.fn();

    const unsubscribe = source.subscribeInvalidations(listener);
    const eventSource = FakeEventSource.instance;
    eventSource?.emit(
      "invalidation",
      JSON.stringify({ scope: "dataset:ds-1", revision: 0, changed_kinds: [] }),
    );
    eventSource?.emit(
      "invalidation",
      JSON.stringify({ scope: "dataset:ds-1", revision: 1, changed_kinds: ["annotation"] }),
    );

    expect(listener).toHaveBeenCalledOnce();
    expect(listener).toHaveBeenCalledWith({
      scope: "dataset:ds-1",
      revision: 1,
      changedKinds: ["annotation"],
    });
    unsubscribe();
    expect(eventSource?.closed).toBe(true);
  });

  it("retries one transient query failure before returning the result", async () => {
    const warning = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    let attempts = 0;
    server.use(
      http.post(QUERY_URL, () => {
        attempts += 1;
        if (attempts === 1) {
          return HttpResponse.json({ detail: "temporarily unavailable" }, { status: 503 });
        }
        return arrowResponse({ group_key: [10], group_count: [2] }, 4);
      }),
    );
    const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId: "ds-1" });
    sources.push(source);

    await expect(source.loadAggregates({ field: "rough_bin" })).resolves.toEqual({ "10": 2 });
    expect(attempts).toBe(2);
    expect(warning).toHaveBeenCalledOnce();
  });

  it("does not retry a deterministic query failure", async () => {
    let attempts = 0;
    server.use(
      http.post(QUERY_URL, () => {
        attempts += 1;
        return HttpResponse.json({ detail: "invalid query" }, { status: 422 });
      }),
    );
    const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId: "ds-1" });
    sources.push(source);

    await expect(source.loadAggregates({ field: "rough_bin" })).rejects.toThrow("invalid query");
    expect(attempts).toBe(1);
  });

  it("includes ordered defect IDs in the Arrow map snapshot", async () => {
    let requestBody: { description: string; sql: string; parameters: unknown[] } | null = null;
    server.use(
      http.post(QUERY_URL, async ({ request }) => {
        requestBody = (await request.json()) as typeof requestBody;
        return arrowResponse({ defect_id: Int32Array.from([3, 9]) }, 1);
      }),
    );
    const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId: "ds-1" });
    sources.push(source);

    await source.loadMap({ legendColumn: "class_number" });

    expect(requestBody).toEqual({
      description: "sc-workbench.map",
      sql: 'SELECT "map_id" AS "defect_id", "wafer_x", "wafer_y", "die_x", "die_y", "reticle_x", "reticle_y", "class_number", "images" FROM samples ORDER BY "defect_id"',
      parameters: [],
    });
  });

  it("normalizes Arrow int64 distinct values for JSON-safe filters", async () => {
    server.use(
      http.post(QUERY_URL, () => arrowResponse({ rough_bin: BigInt64Array.from([1n, 2n]) }, 1)),
    );
    const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId: "ds-1" });
    sources.push(source);

    await expect(
      source.loadDistinctValues({
        field: "rough_bin",
        search: "",
        limit: 20,
        filter: {},
        sort: null,
      }),
    ).resolves.toEqual([1, 2]);
  });

  it("exposes field-specific missing options for derived label fields", async () => {
    const requests: Array<{ sql: string; parameters: unknown[] }> = [];
    server.use(
      http.post(QUERY_URL, async ({ request }) => {
        requests.push((await request.json()) as (typeof requests)[number]);
        return arrowResponse({ prediction_label: [null, "Scratch"] }, 1);
      }),
    );
    const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId: "ds-1" });
    sources.push(source);

    await expect(
      source.loadDistinctValues({
        field: "prediction_label",
        search: "No Prediction",
        limit: 20,
        filter: {},
        sort: null,
      }),
    ).resolves.toEqual(["__no_prediction__", "Scratch"]);
    expect(requests[0]?.sql).not.toContain("CONTAINS");
  });

  it("uses field-specific missing keys in legend aggregates", async () => {
    server.use(
      http.post(QUERY_URL, () =>
        arrowResponse({ group_key: [null, "Scratch"], group_count: [8, 2] }, 1),
      ),
    );
    const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId: "ds-1" });
    sources.push(source);

    await expect(source.loadAggregates({ field: "final_class" })).resolves.toEqual({
      __unclassified__: 8,
      Scratch: 2,
    });
  });

  it("queries numeric field bounds with the active filters", async () => {
    let rangeRequest: { description: string; sql: string; parameters: unknown[] } | null = null;
    server.use(
      http.post(QUERY_URL, async ({ request }) => {
        const body = (await request.json()) as NonNullable<typeof rangeRequest>;
        if (body.description === "sc-workbench.schema") {
          return arrowResponse(
            { area: Float64Array.from([]), class_number: Int32Array.from([]) },
            1,
          );
        }
        rangeRequest = body;
        return arrowResponse({ __min: [1.25], __max: [98.5] }, 1);
      }),
    );
    const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId: "ds-1" });
    sources.push(source);

    await expect(
      source.loadNumericRange({ field: "area", filters: [["class_number", "==", 7]] }),
    ).resolves.toEqual({ min: 1.25, max: 98.5 });
    expect(rangeRequest).toEqual({
      description: "sc-workbench.range.area",
      sql: 'SELECT MIN("area") AS "__min", MAX("area") AS "__max" FROM samples WHERE "class_number" = ?',
      parameters: [7],
    });
  });

  it("loads the full backend schema and includes dynamic metadata in table rows", async () => {
    const requests: Array<{ description: string; sql: string; parameters: unknown[] }> = [];
    server.use(
      http.post(QUERY_URL, async ({ request }) => {
        const body = (await request.json()) as (typeof requests)[number];
        requests.push(body);
        if (body.description === "sc-workbench.schema") {
          return arrowResponse(
            {
              row_key: [] as string[],
              defect_id: Int32Array.from([]),
              future_metric: Float64Array.from([]),
              upstream_payload: [] as string[],
            },
            1,
          );
        }
        if (body.description === "sc-workbench.table.count") {
          return arrowResponse({ __total: BigInt64Array.from([1n]) }, 1);
        }
        return arrowResponse(
          {
            row_key: ["dataset::42"],
            defect_id: Int32Array.from([42]),
            future_metric: Float64Array.from([12.5]),
            upstream_payload: ["kept"],
          },
          1,
        );
      }),
    );
    const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId: "ds-1" });
    sources.push(source);

    await expect(source.loadColumns()).resolves.toEqual([
      {
        name: "row_key",
        arrowType: "Null",
        nullable: true,
        presentation: { ...sampleTableDescriptor.columns[1], order: 1 },
      },
      {
        name: "defect_id",
        arrowType: "Int32",
        nullable: true,
        presentation: { ...sampleTableDescriptor.columns[0], order: 0 },
      },
      { name: "future_metric", arrowType: "Float64", nullable: true },
      { name: "upstream_payload", arrowType: "Null", nullable: true },
    ]);
    const page = await source.loadRows({
      defectIds: [],
      anchor: "0",
      limit: 25,
      filter: {
        future_metric: { filterType: "number", type: "inRange", filter: 10, filterTo: 20 },
      },
      sort: { field: "future_metric", direction: "desc" },
    });

    expect(page.items[0]).toMatchObject({
      row_key: "dataset::42",
      defect_id: "42",
      future_metric: 12.5,
      upstream_payload: "kept",
    });
    expect(requests.map((request) => request.description).sort()).toEqual([
      "sc-workbench.schema",
      "sc-workbench.table.count",
      "sc-workbench.table.rows",
    ]);
    const countRequest = requests.find(
      (request) => request.description === "sc-workbench.table.count",
    );
    expect(countRequest).toEqual({
      description: "sc-workbench.table.count",
      sql: 'SELECT COUNT(*) AS "__total" FROM samples WHERE "future_metric" >= ? AND "future_metric" <= ?',
      parameters: [10, 20],
    });
    const rowsRequest = requests.find(
      (request) => request.description === "sc-workbench.table.rows",
    );
    expect(rowsRequest?.sql).toContain('WITH "__sc_page_ids" AS (SELECT "row_key" FROM samples');
    expect(rowsRequest?.sql).toContain('INNER JOIN "__sc_page_ids" USING ("row_key")');
    expect(rowsRequest?.sql).not.toContain("COUNT(*) OVER");
    expect(rowsRequest?.sql).toContain('ORDER BY "future_metric" DESC, "row_key" ASC');
    expect(rowsRequest?.parameters).toEqual([10, 20, 25, 0]);
  });

  it("rejects a workbench schema without the required physical row key", async () => {
    server.use(
      http.post(QUERY_URL, () =>
        arrowResponse(
          {
            defect_id: Int32Array.from([]),
            sample_id: [] as string[],
          },
          1,
        ),
      ),
    );
    const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId: "ds-1" });
    sources.push(source);

    await expect(source.loadRows({ defectIds: [], anchor: "0", limit: 25 })).rejects.toThrow(
      "missing the required physical row_key column",
    );
  });

  it("reuses the table count until the filter or data revision changes", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const descriptions: string[] = [];
    let revision = 1;
    server.use(
      http.post(QUERY_URL, async ({ request }) => {
        const body = (await request.json()) as { description: string };
        descriptions.push(body.description);
        if (body.description === "sc-workbench.schema") {
          return arrowResponse(
            { row_key: [] as string[], defect_id: Int32Array.from([]) },
            revision,
          );
        }
        if (body.description === "sc-workbench.table.count") {
          return arrowResponse({ __total: BigInt64Array.from([300_000n]) }, revision);
        }
        return arrowResponse(
          { row_key: ["dataset::1"], defect_id: Int32Array.from([1]) },
          revision,
        );
      }),
    );
    const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId: "ds-1" });
    sources.push(source);
    source.subscribeInvalidations(() => undefined);

    await source.loadRows({ defectIds: [], anchor: "0", limit: 250 });
    await source.loadRows({ defectIds: [], anchor: "250", limit: 250 });
    expect(
      descriptions.filter((description) => description === "sc-workbench.table.count"),
    ).toHaveLength(1);

    revision = 2;
    FakeEventSource.instance?.emit(
      "invalidation",
      JSON.stringify({ scope: "dataset:ds-1", revision, changed_kinds: ["annotation"] }),
    );
    await source.loadRows({ defectIds: [], anchor: "500", limit: 250 });

    expect(
      descriptions.filter((description) => description === "sc-workbench.table.count"),
    ).toHaveLength(2);
  });

  it("aborts table count and row fetches when the caller cancels a stale page", async () => {
    server.use(
      http.post(QUERY_URL, () =>
        arrowResponse({ row_key: [] as string[], defect_id: Int32Array.from([]) }, 1),
      ),
    );
    const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId: "ds-1" });
    sources.push(source);
    await source.loadColumns();

    const fetchMock = vi.fn(
      async (_url: RequestInfo | URL, init?: RequestInit) =>
        await new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener(
            "abort",
            () => reject(new DOMException("aborted", "AbortError")),
            { once: true },
          );
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();
    const query = source.loadRows({
      defectIds: [],
      anchor: "250000",
      limit: 250,
      signal: controller.signal,
    });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    controller.abort();

    await expect(query).rejects.toThrow("aborted");
    expect(
      fetchMock.mock.calls.every((call) => (call[1] as RequestInit | undefined)?.signal?.aborted),
    ).toBe(true);
  });

  it("keeps gallery select-all compact and sends only explicit exclusions", async () => {
    const requests: Array<{ sql: string; parameters: unknown[] }> = [];
    server.use(
      http.post(QUERY_URL, async ({ request }) => {
        const body = (await request.json()) as {
          description: string;
          sql: string;
          parameters: unknown[];
        };
        if (body.description === "sc-workbench.schema") {
          return arrowResponse(
            {
              row_key: [] as string[],
              defect_id: Int32Array.from([]),
              rough_bin: Int32Array.from([]),
              annotation_label: [] as string[],
              prediction_label: [] as string[],
              prediction_confidence: Float64Array.from([]),
            },
            1,
          );
        }
        requests.push(body);
        return arrowResponse({ defect_id: Int32Array.from([3]) }, 1);
      }),
    );
    const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId: "ds-1" });
    sources.push(source);

    await source.loadGallery({
      mode: "patch",
      offset: 0,
      limit: 20,
      tableFilter: { rough_bin: { filterType: "set", values: [7] } },
      tableSelection: { kind: "all", excludedIds: [] },
    });
    await source.loadGallery({
      mode: "patch",
      offset: 0,
      limit: 20,
      tableFilter: { rough_bin: { filterType: "set", values: [7] } },
      tableSelection: { kind: "all", excludedIds: ["sample-8", "sample-9"] },
    });

    expect(requests[0]?.sql).not.toContain('defect_id" = ANY');
    expect(requests[0]?.parameters).toEqual([[7], 20, 0]);
    expect(requests[1]?.sql).toContain('NOT ("row_key" = ANY(?))');
    expect(requests[1]?.parameters).toEqual([[7], ["sample-8", "sample-9"], 20, 0]);
  });

  it("treats gallery mode as projection and applies Review membership only from T", async () => {
    const requests: Array<{ sql: string; parameters: unknown[] }> = [];
    server.use(
      http.post(QUERY_URL, async ({ request }) => {
        const body = (await request.json()) as {
          description: string;
          sql: string;
          parameters: unknown[];
        };
        if (body.description === "sc-workbench.schema") {
          return arrowResponse(
            {
              row_key: [] as string[],
              defect_id: Int32Array.from([]),
              images: Int32Array.from([]),
              review_image_ids_json: [] as string[],
              annotation_label: [] as string[],
              prediction_label: [] as string[],
              prediction_confidence: Float64Array.from([]),
            },
            1,
          );
        }
        requests.push(body);
        return arrowResponse({ defect_id: Int32Array.from([3]) }, 1);
      }),
    );
    const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId: "ds-1" });
    sources.push(source);

    await source.loadGallery({ mode: "review", offset: 0, limit: 20 });
    await source.loadGallery({
      mode: "review",
      offset: 0,
      limit: 20,
      filters: [["images", ">", 0]],
    });

    expect(requests[0]?.sql).not.toContain('"images" > ?');
    expect(requests[0]?.parameters).toEqual([20, 0]);
    expect(requests[1]?.sql.match(/"images" > \?/g)).toHaveLength(1);
    expect(requests[1]?.parameters).toEqual([0, 20, 0]);
  });

  it("compiles excluded table-column filters with missing-value semantics", async () => {
    const requests: Array<{ sql: string; parameters: unknown[] }> = [];
    server.use(
      http.post(QUERY_URL, async ({ request }) => {
        const body = (await request.json()) as {
          description: string;
          sql: string;
          parameters: unknown[];
        };
        if (body.description === "sc-workbench.schema") {
          return arrowResponse(
            {
              row_key: [] as string[],
              defect_id: Int32Array.from([]),
              annotation_label: [] as string[],
              prediction_label: [] as string[],
              prediction_confidence: Float64Array.from([]),
            },
            1,
          );
        }
        requests.push(body);
        return arrowResponse({ defect_id: Int32Array.from([3]) }, 1);
      }),
    );
    const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId: "ds-1" });
    sources.push(source);

    await source.loadGallery({
      mode: "patch",
      offset: 0,
      limit: 20,
      tableFilter: { defect_id: { filterType: "set", values: [7, 9], exclude: true } },
    });

    expect(requests[0]?.sql).toContain('(NOT ("defect_id" = ANY(?)) OR "defect_id" IS NULL)');
    expect(requests[0]?.parameters).toEqual([[7, 9], 20, 0]);
  });

  it("discards a response older than the latest observed revision", async () => {
    let revision = 2;
    server.use(
      http.post(QUERY_URL, () => arrowResponse({ group_key: [1], group_count: [1] }, revision)),
    );
    const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId: "ds-1" });
    sources.push(source);

    await source.loadAggregates({ field: "rough_bin" });
    revision = 1;

    await expect(source.loadAggregates({ field: "rough_bin" })).rejects.toThrow(
      "Discarded stale SC data response revision 1",
    );
  });

  it("discards a response invalidated while its Arrow body is streaming", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    let releaseBody: (() => void) | null = null;
    const bodyReleased = new Promise<void>((resolve) => {
      releaseBody = resolve;
    });
    let bodyStarted: (() => void) | null = null;
    const bodyStart = new Promise<void>((resolve) => {
      bodyStarted = resolve;
    });
    const ipc = tableToIPC(tableFromArrays({ group_key: [1], group_count: [1] }));
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        const response = new Response(ipc, {
          headers: {
            "Content-Type": "application/vnd.apache.arrow.stream",
            "X-SC-Data-Revision": "1",
          },
        });
        response.arrayBuffer = async () => {
          bodyStarted?.();
          await bodyReleased;
          return ipc.buffer.slice(ipc.byteOffset, ipc.byteOffset + ipc.byteLength);
        };
        return response;
      }),
    );
    const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId: "ds-1" });
    sources.push(source);
    source.subscribeInvalidations(() => undefined);

    const query = source.loadAggregates({ field: "rough_bin" });
    await bodyStart;
    FakeEventSource.instance?.emit(
      "invalidation",
      JSON.stringify({ scope: "dataset:ds-1", revision: 2, changed_kinds: ["prediction"] }),
    );
    releaseBody?.();

    await expect(query).rejects.toThrow("Discarded stale SC data response revision 1");
  });

  it("aborts active SQL fetches when the data source closes", async () => {
    const fetchMock = vi.fn(
      async (_url: RequestInfo | URL, init?: RequestInit) =>
        await new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener(
            "abort",
            () => reject(new DOMException("aborted", "AbortError")),
            { once: true },
          );
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId: "ds-1" });
    sources.push(source);

    const query = source.loadAggregates({ field: "rough_bin" });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    source.close();

    await expect(query).rejects.toThrow("aborted");
  });

  it("resolves select-all using only defect IDs", async () => {
    let sql = "";
    let description = "";
    server.use(
      http.post(QUERY_URL, async ({ request }) => {
        const body = (await request.json()) as { description: string; sql: string };
        description = body.description;
        sql = body.sql;
        return arrowResponse({ defect_id: Int32Array.from([3, 9]) }, 1);
      }),
    );
    const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId: "ds-1" });
    sources.push(source);

    await expect(
      source.resolveSelection({
        filters: [["rough_bin", "==", 4]],
        constraint: { kind: "all" },
      }),
    ).resolves.toEqual([3, 9]);
    expect(sql).toBe(
      'SELECT "map_id" AS "defect_id" FROM samples WHERE "rough_bin" = ? ORDER BY "map_id"',
    );
    expect(description).toBe("sc-workbench.selection.all");
  });

  it("uses the seed in deterministic random selection", async () => {
    let requestBody: { description: string; sql: string; parameters: unknown[] } | null = null;
    server.use(
      http.post(QUERY_URL, async ({ request }) => {
        requestBody = (await request.json()) as typeof requestBody;
        return arrowResponse({ defect_id: Int32Array.from([9, 3]) }, 1);
      }),
    );
    const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId: "ds-1" });
    sources.push(source);

    await expect(
      source.resolveSelection({
        filters: [["images", ">", 0]],
        constraint: { kind: "random", limit: 2, seed: 42 },
      }),
    ).resolves.toEqual([9, 3]);
    expect(requestBody).toEqual({
      description: "sc-workbench.selection.random",
      sql: 'SELECT "map_id" AS "defect_id" FROM samples WHERE "images" > ? ORDER BY HASH("map_id", ?) LIMIT ?',
      parameters: [0, 42, 2],
    });
  });

  it("sends the candidate query with a structured sampling program", async () => {
    let requestBody: {
      description: string;
      sql: string;
      parameters: unknown[];
      sampling?: { seed: number; program: Record<string, unknown> };
    } | null = null;
    server.use(
      http.post(QUERY_URL, async ({ request }) => {
        requestBody = (await request.json()) as typeof requestBody;
        return arrowResponse({ defect_id: Int32Array.from([8, 2, 5]) }, 1);
      }),
    );
    const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId: "ds-1" });
    sources.push(source);
    const program = createDefaultScSamplingProgram();
    program.conditional = {
      enabled: true,
      field: "rough_bin",
      value: "4",
      limit: 2,
    };
    program.group = {
      enabled: true,
      field: "class_number",
      unit: "count",
      targets: [
        { value: "1", amount: 2 },
        { value: "2", amount: 1 },
      ],
      othersAmount: 0,
      rounding: "nearest",
    };
    program.total.limit = 3;

    await expect(
      source.resolveSelection({
        filters: [["images", ">", 0]],
        constraint: { kind: "sampling-program", program, seed: 42 },
      }),
    ).resolves.toEqual([8, 2, 5]);

    expect(requestBody?.description).toBe("sc-workbench.selection.sampling-program");
    expect(requestBody?.sql).toBe(
      'SELECT "map_id", "rough_bin", "class_number" FROM samples WHERE "images" > ?',
    );
    expect(requestBody?.parameters).toEqual([0]);
    expect(requestBody?.sampling).toEqual({
      seed: 42,
      program: {
        conditional: program.conditional,
        group: program.group,
        total: program.total,
      },
    });
  });

  it("keeps ratio and Others semantics in the structured backend program", () => {
    const program = createDefaultScSamplingProgram();
    program.group = {
      enabled: true,
      field: "class_number",
      unit: "ratio",
      targets: [{ value: "1", amount: 2 }],
      othersAmount: 5,
      rounding: "nearest",
    };

    const compiled = compileScSamplingSelection([], program, 42);

    expect(compiled.sql).toBe('SELECT "map_id", "class_number" FROM samples');
    expect(compiled.parameters).toEqual([]);
    expect(compiled.sampling).toEqual({
      seed: 42,
      program: {
        conditional: program.conditional,
        group: program.group,
        total: program.total,
      },
    });
  });

  it("accepts only valid invalidations for its own scope", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId: "ds-1" });
    sources.push(source);
    const listener = vi.fn();

    source.subscribeInvalidations(listener);
    FakeEventSource.instance?.emit("invalidation", "not-json");
    FakeEventSource.instance?.emit(
      "invalidation",
      JSON.stringify({ scope: "dataset:other", revision: 2, changed_kinds: ["prediction"] }),
    );
    FakeEventSource.instance?.emit(
      "invalidation",
      JSON.stringify({ scope: "dataset:ds-1", revision: 3, changed_kinds: ["annotation"] }),
    );

    expect(listener).toHaveBeenCalledOnce();
    expect(listener).toHaveBeenCalledWith({
      scope: "dataset:ds-1",
      revision: 3,
      changedKinds: ["annotation"],
    });
  });
});
