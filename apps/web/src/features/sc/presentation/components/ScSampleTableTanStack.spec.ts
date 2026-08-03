import { describe, expect, it, vi } from "vitest";
import type { ScSampleTableDisplayRow } from "@/features/sc/domain/workbenchInteraction";
import type { ScSampleTableDataSource } from "@/features/sc/domain/workbenchInteraction";
import { mountWithProviders } from "@/testing";
import ScSampleTableTanStack from "./ScSampleTableTanStack.vue";

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

describe("ScSampleTableTanStack", () => {
  it("keeps 300k select-all symbolic", async () => {
    const loadRows = vi.fn<ScSampleTableDataSource["loadRows"]>(async () => ({
      items: [sampleRow("11", 1), sampleRow("12", 1)],
      total: 300_000,
      nextAnchor: "2",
    }));
    const dataSource: ScSampleTableDataSource = { scopeKey: "dataset:one", loadRows };
    const { wrapper } = await mountWithProviders(ScSampleTableTanStack, {
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
    const dataSource: ScSampleTableDataSource = { scopeKey: "dataset:sort", loadRows };
    const { wrapper } = await mountWithProviders(ScSampleTableTanStack, {
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
        { name: "defect_id", arrowType: "Int32", nullable: false },
        { name: "future_metric", arrowType: "Float64", nullable: true },
      ],
      loadRows,
    };
    const { wrapper } = await mountWithProviders(ScSampleTableTanStack, {
      props: { dataSource },
    });

    await vi.waitFor(() => expect(wrapper.text()).toContain("future_metric"));
    expect(wrapper.text()).toContain("12.5");
  });
});
