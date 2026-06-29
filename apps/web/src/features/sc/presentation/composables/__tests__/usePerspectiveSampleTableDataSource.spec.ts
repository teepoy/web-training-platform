import { describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import type { Filter, Table, View } from "@perspective-dev/client";
import { usePerspectiveSampleTableDataSource } from "../usePerspectiveSampleTableDataSource";

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

  it("loads rows from an active prebuilt view without rebuilding a table view", async () => {
    const tableView = vi.fn();
    const table = ref({ view: tableView } as unknown as Table);
    const scopeKey = ref("scope");
    const baseFilters = ref<Filter[]>([]);
    const activeView = ref({
      num_rows: vi.fn(async () => 2),
      to_columns: vi.fn(async () => ({
        defect_id: [11, 12],
        rough_bin: [1, 2],
        class_number: [3, 4],
      })),
    } as unknown as View);
    const activeViewVersion = ref(7);
    const dataSource = usePerspectiveSampleTableDataSource(
      table,
      scopeKey,
      baseFilters,
      activeView,
      activeViewVersion,
    );

    expect(dataSource.value?.scopeKey).toBe("scope:[]:view:7");

    const page = await dataSource.value!.loadRows({
      defectIds: [],
      anchor: "0",
      limit: 1000,
    });

    expect(tableView).not.toHaveBeenCalled();
    expect(page.total).toBe(2);
    expect(page.items.map((row) => row.defect_id)).toEqual(["11", "12"]);
  });
});
