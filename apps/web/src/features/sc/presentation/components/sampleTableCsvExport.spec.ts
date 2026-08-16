import { describe, expect, it, vi } from "vitest";
import type {
  ScSampleTableDataSource,
  ScSampleTableDisplayRow,
} from "@/features/sc/domain/workbenchInteraction";
import {
  csvCell,
  exportSampleTableCsv,
  sampleTableCsvFileName,
  serializeSampleTableCsvRows,
} from "./sampleTableCsvExport";

function row(id: string, note: string): ScSampleTableDisplayRow {
  return {
    row_key: `row-${id}`,
    defect_id: id,
    rough_bin: 0,
    class_number: 0,
    images: 0,
    test_id: 0,
    wafer_x: 0,
    wafer_y: 0,
    index_x: 0,
    index_y: 0,
    adder: 0,
    die_x: 0,
    die_y: 0,
    reticle_x: 0,
    reticle_y: 0,
    size_x: 0,
    size_y: 0,
    size_d: 0,
    area: 0,
    final_bin: 0,
    manual_bin: 0,
    note,
  };
}

describe("sampleTableCsvExport", () => {
  it("escapes CSV syntax and neutralizes spreadsheet formulas", () => {
    expect(csvCell('a,"b"\nc')).toBe('"a,""b""\nc"');
    expect(csvCell('=HYPERLINK("https://example.test")')).toBe(
      '"\'=HYPERLINK(""https://example.test"")"',
    );
    expect(csvCell(-12)).toBe("-12");
    expect(
      serializeSampleTableCsvRows(
        [
          { key: "defect_id", title: "Defect ID" },
          { key: "note", title: "Note" },
        ],
        [row("7", "hello, world")],
        true,
      ),
    ).toBe('Defect ID,Note\r\n7,"hello, world"\r\n');
  });

  it("loads every page with the current filter and stable sort", async () => {
    const loadRows = vi.fn<ScSampleTableDataSource["loadRows"]>(async (query) =>
      query.anchor === "0"
        ? { items: [row("1", "one"), row("2", "two")], total: 3, nextAnchor: "2" }
        : { items: [row("3", "three")], total: 3, nextAnchor: null },
    );
    const progress = vi.fn();
    const filter = {
      images: { filterType: "number" as const, type: "inRange" as const, filter: 1, filterTo: 5 },
    };
    const sort = { field: "images", direction: "desc" as const };

    const result = await exportSampleTableCsv({
      dataSource: { scopeKey: "inspection:test", loadRows },
      columns: [{ key: "defect_id", title: "Defect ID" }],
      defectIds: [],
      filter,
      sort,
      batchRows: 2,
      onProgress: progress,
    });

    expect(loadRows).toHaveBeenCalledTimes(2);
    expect(loadRows.mock.calls.map(([query]) => query.anchor)).toEqual(["0", "2"]);
    expect(loadRows.mock.calls[0]?.[0]).toMatchObject({ limit: 2, filter, sort });
    expect(await result.blob.text()).toBe("\uFEFFDefect ID\r\n1\r\n2\r\n3\r\n");
    expect(progress).toHaveBeenLastCalledWith({ completed: 3, total: 3 });
  });

  it("fails rather than mixing pages when the source changes", async () => {
    const loadRows = vi.fn<ScSampleTableDataSource["loadRows"]>(async (query) =>
      query.anchor === "0"
        ? { items: [row("1", "one")], total: 2, nextAnchor: "1" }
        : { items: [row("2", "two")], total: 3, nextAnchor: null },
    );

    await expect(
      exportSampleTableCsv({
        dataSource: { scopeKey: "inspection:test", loadRows },
        columns: [{ key: "defect_id", title: "Defect ID" }],
        defectIds: [],
        filter: {},
        sort: { field: "defect_id", direction: "asc" },
      }),
    ).rejects.toThrow("Sample data changed during export");
  });

  it("creates a filesystem-safe CSV filename", () => {
    expect(sampleTableCsvFileName("inspection:2026-08-17 12:30/1")).toBe(
      "inspection-2026-08-17-12-30-1.csv",
    );
  });
});
