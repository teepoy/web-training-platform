import { flushPromises } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { HttpResponse, http } from "msw";
import { mountWithProviders } from "@/testing";
import { server } from "@/testing/msw/server";
import ScSampleTable from "../ScSampleTable.vue";

function makeRow(defectId: number) {
  return {
    defect_id: String(defectId),
    rough_bin: defectId,
    class_number: defectId,
    test_id: defectId,
    wafer_x: defectId,
    wafer_y: defectId,
    index_x: defectId,
    index_y: defectId,
    adder: 0,
    cluster_id: 0,
    die_x: defectId,
    die_y: defectId,
    size_x: 100,
    size_y: 200,
    size_d: 224,
    area: 20_000,
    final_bin: 1,
    manual_bin: 2,
    kill_ratio: 0.5,
  };
}

function sampleTableStream(rows: ReturnType<typeof makeRow>[]) {
  return [
    'event: progress\ndata: {"event_type":"progress","status":"loading","operation":"sc.sample-table"}\n\n',
    `event: data\ndata: ${JSON.stringify({
      event_type: "data",
      operation: "sc.sample-table",
      payload: {
        items: rows,
        total: rows.length,
        next_anchor: null,
      },
    })}\n\n`,
    'event: done\ndata: {"event_type":"done"}\n\n',
  ].join("");
}

describe("ScSampleTable", () => {
  it("sends controlled filter and sort parameters to the rows API", async () => {
    const requestBody = vi.fn();
    server.use(
      http.post(
        "/api/v1/sc/inspections/:inspectionTime/:waferKey/sample-table-rows/stream",
        async ({ request }) => {
          requestBody(await request.json());
          return new HttpResponse(sampleTableStream([makeRow(9)]), {
            headers: { "Content-Type": "text/event-stream" },
          });
        },
      ),
    );

    await mountWithProviders(ScSampleTable, {
      props: {
        inspectionTime: "2026-01-01T00:00:00",
        waferKey: 1,
        loading: false,
        total: 10,
        filter: {
          rough_bin: { operator: "in", values: [1, 5] },
          wafer_x: { operator: "between", min: -100, max: 100 },
        },
        sort: { field: "defect_id", direction: "desc" },
      },
    });
    await flushPromises();

    expect(requestBody).toHaveBeenCalledTimes(1);
    expect(requestBody.mock.calls[0][0]).not.toHaveProperty("defect_ids");
    expect(requestBody.mock.calls[0][0]).not.toHaveProperty(
      "reticle_x_die_count",
    );
    expect(requestBody).toHaveBeenCalledWith(
      expect.objectContaining({
        anchor: "0",
        limit: 100,
        filter: {
          rough_bin: { operator: "in", values: [1, 5] },
          wafer_x: { operator: "between", min: -100, max: 100 },
        },
        sort: { field: "defect_id", direction: "desc" },
      }),
    );
  });

  it("uses controlled sort, set filters, range filters, and selection", async () => {
    server.use(
      http.post(
        "/api/v1/sc/inspections/:inspectionTime/:waferKey/sample-table-rows/stream",
        () =>
          new HttpResponse(sampleTableStream([makeRow(1), makeRow(2)]), {
            headers: { "Content-Type": "text/event-stream" },
          }),
      ),
    );
    const { wrapper } = await mountWithProviders(ScSampleTable, {
      props: {
        inspectionTime: "2026-01-01T00:00:00",
        waferKey: 1,
        loading: false,
        total: 2,
        selectedDefectIds: new Set([2]),
        filter: {
          rough_bin: { operator: "in", values: [2] },
          wafer_x: { operator: "between", min: 1, max: 2 },
        },
        sort: { field: "wafer_y", direction: "asc" },
      },
    });
    await flushPromises();

    const table = wrapper.findComponent({ name: "DataTable" });
    expect(table.exists()).toBe(true);
    expect(table.props("virtualScroll")).toBe(true);
    expect(table.props("virtualScrollX")).toBe(true);
    expect(table.props("checkedRowKeys")).toEqual([2]);

    const dataColumns = (
      table.props("columns") as Array<Record<string, unknown>>
    ).filter((column) => column.type !== "selection");
    expect(dataColumns).toHaveLength(19);
    expect(dataColumns.every((column) => column.sorter === true)).toBe(true);

    const roughBinColumn = dataColumns.find(
      (column) => column.key === "rough_bin",
    );
    expect(roughBinColumn?.filterOptionValues).toEqual([2]);
    expect(roughBinColumn?.filterOptions).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ label: "1", value: 1 }),
        expect.objectContaining({ label: "2", value: 2 }),
      ]),
    );

    const waferXColumn = dataColumns.find((column) => column.key === "wafer_x");
    expect(waferXColumn?.filterOptionValues).toEqual([1, 2]);
    expect(waferXColumn?.filterOptions).toBeUndefined();
    expect(waferXColumn?.renderFilterMenu).toEqual(expect.any(Function));

    const waferYColumn = dataColumns.find((column) => column.key === "wafer_y");
    expect(waferYColumn?.sortOrder).toBe("ascend");

    table.vm.$emit(
      "update:filters",
      { rough_bin: [1, 2], wafer_x: [1, 2] },
      roughBinColumn,
    );
    await flushPromises();
    expect(wrapper.emitted("filter-change")?.at(-1)?.[0]).toEqual({
      rough_bin: { operator: "in", values: [1, 2] },
      wafer_x: { operator: "between", min: 1, max: 2 },
    });

    table.vm.$emit("update:sorter", {
      columnKey: "area",
      order: "descend",
      sorter: true,
    });
    await flushPromises();
    expect(wrapper.emitted("sort-change")?.at(-1)?.[0]).toEqual({
      field: "area",
      direction: "desc",
    });

    table.vm.$emit("update:checked-row-keys", [1, 2]);
    await flushPromises();

    expect(wrapper.emitted("selection-change")?.at(-1)?.[0]).toEqual([1, 2]);
  });
});
