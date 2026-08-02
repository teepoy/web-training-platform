import { tableFromArrays, tableToIPC } from "apache-arrow";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { server } from "@/testing/msw/server";
import { compileScWhere, SqlWorkbenchDataSource } from "./sqlWorkbenchDataSource";

const QUERY_URL = "/api/v1/sc/data/datasets/ds-1/query";

class FakeEventSource {
  static instance: FakeEventSource | null = null;
  private readonly listeners = new Map<string, (event: MessageEvent<string>) => void>();

  constructor(readonly url: string) {
    FakeEventSource.instance = this;
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
    this.listeners.set(type, listener as (event: MessageEvent<string>) => void);
  }

  close(): void {
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
      ]),
    ).toEqual({
      sql: ' WHERE "rough_bin" = ANY(?) AND NOT ("defect_id" = ANY(?)) AND CONTAINS(CAST("prediction_label" AS VARCHAR), ?) AND "annotation_label" IS NULL',
      parameters: [[1, 2], [8, 9], "scratch"],
    });

    expect(() => compileScWhere([["secret_path", "==", "/etc/passwd"]])).toThrow(
      "Unsupported SC data field",
    );
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
      sql: 'SELECT "defect_id", "wafer_x", "wafer_y", "die_x", "die_y", "reticle_x", "reticle_y", "class_number", "images" FROM samples ORDER BY "defect_id"',
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

  it("loads the full backend schema and includes dynamic metadata in table rows", async () => {
    const requests: Array<{ description: string; sql: string; parameters: unknown[] }> = [];
    server.use(
      http.post(QUERY_URL, async ({ request }) => {
        const body = (await request.json()) as (typeof requests)[number];
        requests.push(body);
        if (body.description === "sc-workbench.schema") {
          return arrowResponse(
            {
              defect_id: Int32Array.from([]),
              future_metric: Float64Array.from([]),
              upstream_payload: [] as string[],
            },
            1,
          );
        }
        return arrowResponse(
          {
            defect_id: Int32Array.from([42]),
            future_metric: Float64Array.from([12.5]),
            upstream_payload: ["kept"],
            __total: BigInt64Array.from([1n]),
          },
          1,
        );
      }),
    );
    const source = new SqlWorkbenchDataSource({ kind: "dataset", datasetId: "ds-1" });
    sources.push(source);

    await expect(source.loadColumns()).resolves.toEqual([
      { name: "defect_id", arrowType: "Int32", nullable: true },
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
      defect_id: "42",
      future_metric: 12.5,
      upstream_payload: "kept",
    });
    expect(requests.map((request) => request.description)).toEqual([
      "sc-workbench.schema",
      "sc-workbench.table.rows",
    ]);
    expect(requests[1]?.sql).toContain('"future_metric"');
    expect(requests[1]?.sql).toContain('ORDER BY "future_metric" DESC');
    expect(requests[1]?.parameters).toEqual([10, 20, 25, 0]);
  });

  it("keeps gallery select-all compact and sends only explicit exclusions", async () => {
    const requests: Array<{ sql: string; parameters: unknown[] }> = [];
    server.use(
      http.post(QUERY_URL, async ({ request }) => {
        requests.push((await request.json()) as { sql: string; parameters: unknown[] });
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
      tableSelection: { kind: "all", excludedIds: [8, 9] },
    });

    expect(requests[0]?.sql).not.toContain('defect_id" = ANY');
    expect(requests[0]?.parameters).toEqual([[7], 20, 0]);
    expect(requests[1]?.sql).toContain('NOT ("defect_id" = ANY(?))');
    expect(requests[1]?.parameters).toEqual([[7], [8, 9], 20, 0]);
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
    expect(sql).toBe('SELECT "defect_id" FROM samples WHERE "rough_bin" = ? ORDER BY "defect_id"');
    expect(description).toBe("sc-workbench.selection.all");
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
