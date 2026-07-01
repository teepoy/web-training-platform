import { describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import type { Filter, Table, View } from "@perspective-dev/client";
import { usePerspectiveSampleTableDataSource } from "../usePerspectiveSampleTableDataSource";

const arrowMock = vi.hoisted(() => ({
  rows: [] as Array<Record<string, unknown>>,
}));

vi.mock("apache-arrow", () => ({
  tableFromIPC: vi.fn(() => ({
    toArray: () => arrowMock.rows.map((row) => ({ toJSON: () => row })),
  })),
}));

describe("usePerspectiveSampleTableDataSource", () => {
  it("changes scope key when base filters change", () => {
    const table = ref({} as Table);
    const scopeKey = ref("scope");
    const baseFilters = ref<Filter[]>([]);
    const dataSource = usePerspectiveSampleTableDataSource(table, scopeKey, baseFilters);

    expect(dataSource.value?.scopeKey).toBe("scope:[]:table");

    baseFilters.value = [["map_in_selection", "==", 1] as Filter];

    expect(dataSource.value?.scopeKey).toBe('scope:[["map_in_selection","==",1]]:table');
  });

  it("reuses the current filtered rows view while paging the same config", async () => {
    const rowsView = {
      num_rows: vi.fn(async () => 2),
      to_arrow: vi.fn(async () => new Uint8Array()),
    } as unknown as View;
    arrowMock.rows = [
      { defect_id: 11, rough_bin: 1, class_number: 3 },
      { defect_id: 12, rough_bin: 2, class_number: 4 },
    ];
    const tableView = vi.fn(async () => rowsView);
    const table = ref({ view: tableView } as unknown as Table);
    const scopeKey = ref("scope");
    const baseFilters = ref<Filter[]>([["map_in_selection", "==", 1] as Filter]);
    const dataSource = usePerspectiveSampleTableDataSource(table, scopeKey, baseFilters);

    expect(dataSource.value?.scopeKey).toBe('scope:[["map_in_selection","==",1]]:table');

    const page = await dataSource.value!.loadRows({
      defectIds: [],
      anchor: "0",
      limit: 1000,
    });
    const nextPage = await dataSource.value!.loadRows({
      defectIds: [],
      anchor: "1",
      limit: 1000,
    });

    expect(tableView).toHaveBeenCalledTimes(1);
    expect(page.total).toBe(2);
    expect(nextPage.total).toBe(2);
    expect(page.items.map((row) => row.defect_id)).toEqual(["11", "12"]);
  });

  it("reports recoverable Perspective failures from row loading", async () => {
    const err = new WebAssembly.RuntimeError("memory access out of bounds");
    const onRecoverableError = vi.fn();
    const table = ref({
      view: vi.fn(async () => {
        throw err;
      }),
    } as unknown as Table);
    const scopeKey = ref("scope");
    const dataSource = usePerspectiveSampleTableDataSource(
      table,
      scopeKey,
      undefined,
      onRecoverableError,
    );

    await expect(
      dataSource.value!.loadRows({
        defectIds: [],
        anchor: "0",
        limit: 1000,
      }),
    ).rejects.toBe(err);

    expect(onRecoverableError).toHaveBeenCalledWith("sample table rows load failed", err);
  });
});
