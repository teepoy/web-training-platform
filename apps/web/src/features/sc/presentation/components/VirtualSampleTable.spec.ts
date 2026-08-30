import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NPopover } from "naive-ui";
import type { ScSampleTableDisplayRow } from "@/features/sc/domain/workbenchInteraction";
import type { ScSampleTableDataSource } from "@/features/sc/domain/workbenchInteraction";
import type { ScDataColumn } from "@/features/sc/domain/workbenchDataSource";
import { mountWithProviders } from "@/testing";
import VirtualSampleTable from "./VirtualSampleTable.vue";

vi.mock("@tanstack/vue-virtual", () => ({
  useVirtualizer: (options: {
    count: number;
    estimateSize: (index: number) => number;
    getItemKey?: (index: number) => string | number;
    horizontal?: boolean;
    paddingStart?: number;
  }) => {
    const inner = {
      getVirtualItems: () => {
        const count = Math.min(options.count, options.horizontal ? 12 : 10);
        let start = options.paddingStart ?? 0;
        return Array.from({ length: count }, (_, index) => {
          const size = options.estimateSize(index);
          const item = {
            index,
            key: options.getItemKey?.(index) ?? index,
            size,
            start,
          };
          start += size;
          return item;
        });
      },
      getTotalSize: () => {
        let total = options.paddingStart ?? 0;
        for (let index = 0; index < options.count; index += 1) {
          total += options.estimateSize(index);
        }
        return total;
      },
    };
    return { value: inner };
  },
}));

function sampleRow(defectId: string, images: number): ScSampleTableDisplayRow {
  return {
    row_key: `dataset::${defectId}`,
    defect_id: defectId,
    rough_bin: 0,
    class_number: 0,
    images,
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
  };
}

function describedColumn(
  name: string,
  title: string,
  order: number,
  visibility: NonNullable<ScDataColumn["presentation"]>["visibility"] = "default",
): ScDataColumn {
  return {
    name,
    arrowType: "Int32",
    nullable: false,
    presentation: {
      title,
      width: 120,
      filter: visibility === "internal" ? null : "range",
      visibility,
      format: "plain",
      order,
    },
  };
}

const defaultColumns = [
  describedColumn("defect_id", "Defect ID", 0),
  describedColumn("images", "Images", 1),
];

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("VirtualSampleTable", () => {
  it("loads observed numeric bounds when a range filter opens", async () => {
    const loadRows = vi.fn<ScSampleTableDataSource["loadRows"]>(async () => ({
      items: [sampleRow("11", 2)],
      total: 1,
      nextAnchor: null,
    }));
    const loadNumericRange = vi.fn(async () => ({ min: 0, max: 10 }));
    const dataSource: ScSampleTableDataSource = {
      scopeKey: "inspection:numeric-range",
      loadColumns: async () => defaultColumns,
      loadRows,
      loadNumericRange,
    };
    const { wrapper } = await mountWithProviders(VirtualSampleTable, { props: { dataSource } });
    await vi.waitFor(() => expect(loadRows).toHaveBeenCalledOnce());
    await vi.waitFor(() => expect(wrapper.findAllComponents(NPopover).length).toBeGreaterThan(1));

    wrapper.findAllComponents(NPopover).at(-1)!.vm.$emit("update:show", true);
    await vi.waitFor(() => expect(loadNumericRange).toHaveBeenCalledOnce());
    expect(loadNumericRange).toHaveBeenCalledWith({
      field: "images",
      filter: {},
      sort: { field: "defect_id", direction: "asc" },
    });
  });

  it("keeps row hover backgrounds compatible with the Chrome 108 target", () => {
    const source = readFileSync(
      resolve(process.cwd(), "src/features/sc/presentation/components/VirtualSampleTable.vue"),
      "utf8",
    );

    expect(source).not.toContain(
      "background: color-mix(in srgb, var(--sst-row-background) 94%, currentColor 6%)",
    );
    expect(source).toContain("background-color: var(--sst-row-background)");
    expect(source).toContain(
      "background-image: linear-gradient(rgba(127, 127, 127, 0.1), rgba(127, 127, 127, 0.1))",
    );
  });

  it("uses the shared primary quaternary icon style for clear selection", async () => {
    const loadRows = vi.fn<ScSampleTableDataSource["loadRows"]>(async () => ({
      items: [sampleRow("11", 1)],
      total: 1,
      nextAnchor: null,
    }));
    const dataSource: ScSampleTableDataSource = {
      scopeKey: "dataset:selection-action",
      loadColumns: async () => defaultColumns,
      loadRows,
    };
    const { wrapper } = await mountWithProviders(VirtualSampleTable, {
      props: { dataSource, enableSelection: true },
    });

    await vi.waitFor(() => expect(loadRows).toHaveBeenCalledOnce());
    await wrapper.get<HTMLInputElement>('input[aria-label="Select sample 11"]').setValue(true);

    const clearSelection = wrapper.get('[data-testid="clear-sample-selection"]');
    expect(clearSelection.classes()).toContain("n-button--primary-type");
    expect(clearSelection.attributes("aria-label")).toBe("Clear selection (1)");
    expect(clearSelection.find("svg").exists()).toBe(true);
  });

  it("keeps the pinned selection and Defect ID cells in the same row", async () => {
    const loadRows = vi.fn<ScSampleTableDataSource["loadRows"]>(async () => ({
      items: [sampleRow("11", 1)],
      total: 1,
      nextAnchor: null,
    }));
    const dataSource: ScSampleTableDataSource = {
      scopeKey: "dataset:layout",
      loadColumns: async () => defaultColumns,
      loadRows,
    };
    const { wrapper } = await mountWithProviders(VirtualSampleTable, {
      props: { dataSource, enableSelection: true },
    });

    await vi.waitFor(() => expect(loadRows).toHaveBeenCalledTimes(1));

    expect(wrapper.get(".sst-tanstack-header").attributes("style")).toContain("display: flex");
    expect(wrapper.get(".sst-tanstack-row").attributes("style")).toContain("display: flex");
  });

  it("exports the complete current table query as CSV", async () => {
    const loadRows = vi.fn<ScSampleTableDataSource["loadRows"]>(async () => ({
      items: [sampleRow("11", 1)],
      total: 1,
      nextAnchor: null,
    }));
    const dataSource: ScSampleTableDataSource = {
      scopeKey: "inspection:export",
      loadColumns: async () => defaultColumns,
      loadRows,
    };
    const createObjectURL = vi.fn(() => "blob:sample-export");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const downloads: Array<{ download: string; href: string }> = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function () {
      downloads.push({ download: this.download, href: this.href });
    });
    const filter = {
      images: {
        filterType: "number" as const,
        type: "inRange" as const,
        filter: 1,
        filterTo: 2,
      },
    };

    const { wrapper } = await mountWithProviders(VirtualSampleTable, {
      props: {
        dataSource,
        exportFileName: "inspection:export sample data",
        filter,
        sort: { field: "images", direction: "desc" },
      },
    });
    await vi.waitFor(() => expect(loadRows).toHaveBeenCalledOnce());

    await wrapper.get('[data-testid="export-sample-data-csv"]').trigger("click");

    await vi.waitFor(() => expect(wrapper.text()).toContain("Exported 1 rows"));
    expect(loadRows).toHaveBeenCalledTimes(2);
    expect(loadRows.mock.calls[1]?.[0]).toMatchObject({
      anchor: "0",
      limit: 10_000,
      filter,
      sort: { field: "images", direction: "desc" },
    });
    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(downloads).toEqual([
      { download: "inspection-export-sample-data.csv", href: "blob:sample-export" },
    ]);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:sample-export");
  });

  it("keeps 300k select-all symbolic", async () => {
    const loadRows = vi.fn<ScSampleTableDataSource["loadRows"]>(async () => ({
      items: [sampleRow("11", 1), sampleRow("12", 1)],
      total: 300_000,
      nextAnchor: "2",
    }));
    const dataSource: ScSampleTableDataSource = {
      scopeKey: "dataset:one",
      loadColumns: async () => defaultColumns,
      loadRows,
    };
    const { wrapper } = await mountWithProviders(VirtualSampleTable, {
      props: { dataSource, enableSelection: true },
    });

    await vi.waitFor(() => expect(loadRows).toHaveBeenCalledTimes(1));
    const selectAll = wrapper.get<HTMLInputElement>('input[aria-label="Select all sample rows"]');
    await selectAll.setValue(true);

    expect(wrapper.emitted("selection-change")).toEqual([[{ kind: "all", excludedIds: [] }]]);
    expect(loadRows).toHaveBeenCalledTimes(1);
  });

  it("uses controlled server sorting and renders the returned order", async () => {
    const loadRows = vi.fn<ScSampleTableDataSource["loadRows"]>(async (query) => ({
      items:
        query.sort?.field === "images"
          ? [sampleRow("2", 1), sampleRow("1", 2)]
          : [sampleRow("1", 2), sampleRow("2", 1)],
      total: 2,
      nextAnchor: null,
    }));
    const dataSource: ScSampleTableDataSource = {
      scopeKey: "dataset:sort",
      loadColumns: async () => defaultColumns,
      loadRows,
    };
    const { wrapper } = await mountWithProviders(VirtualSampleTable, {
      props: { dataSource },
    });

    await vi.waitFor(() => expect(wrapper.text()).toContain("Sample Data (2)"));
    const imagesSort = wrapper
      .findAll(".sst-tanstack-sort-button")
      .find((button) =>
        button.element.closest('[role="columnheader"]')?.textContent?.includes("Images"),
      );
    expect(imagesSort).toBeDefined();
    await imagesSort?.trigger("click");

    await vi.waitFor(() => expect(loadRows).toHaveBeenCalledTimes(2));
    expect(loadRows.mock.calls[1]?.[0].sort).toEqual({ field: "images", direction: "asc" });
    await vi.waitFor(() => expect(wrapper.text()).toContain("2"));
  });

  it("renders arbitrary metadata columns returned by the data source schema", async () => {
    const loadRows = vi.fn<ScSampleTableDataSource["loadRows"]>(async () => ({
      items: [{ ...sampleRow("1", 2), future_metric: 12.5 }],
      total: 1,
      nextAnchor: null,
    }));
    const dataSource: ScSampleTableDataSource = {
      scopeKey: "dataset:dynamic",
      loadColumns: async () => [
        describedColumn("defect_id", "Defect ID", 0),
        { name: "future_metric", arrowType: "Float64", nullable: true },
      ],
      loadRows,
    };
    const { wrapper } = await mountWithProviders(VirtualSampleTable, {
      props: { dataSource },
    });

    await vi.waitFor(() => expect(wrapper.text()).toContain("future_metric"));
    expect(wrapper.text()).toContain("12.5");
  });

  it("keeps columns when a same-scope data-source wrapper changes during loading", async () => {
    let resolveColumns!: (columns: ScDataColumn[]) => void;
    const loadColumns = vi.fn(
      () => new Promise<ScDataColumn[]>((resolve) => (resolveColumns = resolve)),
    );
    const loadRows = vi.fn<ScSampleTableDataSource["loadRows"]>(async () => ({
      items: [sampleRow("11", 2)],
      total: 1,
      nextAnchor: null,
    }));
    const firstDataSource: ScSampleTableDataSource = {
      scopeKey: "dataset:same-scope",
      loadColumns,
      loadRows,
    };
    const secondDataSource: ScSampleTableDataSource = {
      scopeKey: "dataset:same-scope",
      loadColumns,
      loadRows,
    };
    const { wrapper } = await mountWithProviders(VirtualSampleTable, {
      props: { dataSource: firstDataSource, enableSelection: true },
    });

    await vi.waitFor(() => expect(loadRows).toHaveBeenCalledOnce());
    await wrapper.setProps({ dataSource: secondDataSource });
    resolveColumns(defaultColumns);

    await vi.waitFor(() => expect(wrapper.text()).toContain("Images"));
    expect(wrapper.text()).toContain("11");
    expect(wrapper.text()).toContain("2");
    expect(loadColumns).toHaveBeenCalledOnce();
  });

  it("shows the stable row key as Sample ID so duplicate defect IDs stay distinguishable", async () => {
    const loadRows = vi.fn<ScSampleTableDataSource["loadRows"]>(async () => ({
      items: [
        { ...sampleRow("1", 0), row_key: "dataset-a::sample-1" },
        { ...sampleRow("1", 0), row_key: "dataset-b::sample-1" },
      ],
      total: 2,
      nextAnchor: null,
    }));
    const dataSource: ScSampleTableDataSource = {
      scopeKey: "collection:identity",
      loadColumns: async () => [
        describedColumn("row_key", "Sample ID", 1),
        describedColumn("map_id", "Map ID", 5, "internal"),
        describedColumn("defect_id", "Defect ID", 0),
        describedColumn("sample_id", "Sample ID", 6, "internal"),
        describedColumn("source_sample_id", "Source Sample ID", 7, "internal"),
      ],
      loadRows,
    };
    const { wrapper } = await mountWithProviders(VirtualSampleTable, {
      props: { dataSource },
    });

    await vi.waitFor(() => expect(wrapper.text()).toContain("Sample ID"));
    expect(wrapper.text()).toContain("dataset-a::sample-1");
    expect(wrapper.text()).toContain("dataset-b::sample-1");
    expect(wrapper.text()).not.toContain("map_id");
  });
});
