import { defineComponent } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ScSampleTableDisplayRow } from "@/features/sc/domain/workbenchInteraction";
import type { ScSampleTableDataSource } from "@/features/sc/domain/workbenchInteraction";
import { mountWithProviders } from "@/testing";
import { SC_SCROLL_QUERY_DEBOUNCE_MS } from "../composables/scrollQueryDebounce";
import ScSampleTableVxe from "./ScSampleTableVxe.vue";

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

function tableStubs(loadData: ReturnType<typeof vi.fn>) {
  const VxeTable = defineComponent({
    name: "VxeTable",
    inheritAttrs: false,
    emits: ["checkbox-change", "checkbox-all", "cell-click", "scroll"],
    setup(_props, { expose, slots }) {
      expose({
        clearCheckboxRow: vi.fn(),
        getScrollData: vi.fn(() => ({
          clientWidth: 400,
          scrollLeft: 120,
          scrollWidth: 2_400,
        })),
        loadData,
        recalculate: vi.fn(async () => undefined),
        refreshScroll: vi.fn(async () => undefined),
        reloadData: vi.fn(async () => undefined),
        scrollTo: vi.fn(async () => undefined),
        setCheckboxRowKey: vi.fn(),
      });
      return () => slots.default?.();
    },
  });
  const VxeColumn = defineComponent({
    name: "VxeColumn",
    inheritAttrs: false,
    setup(_props, { slots }) {
      return () => slots.header?.();
    },
  });
  return { VxeTable, VxeColumn };
}

describe("ScSampleTableVxe server query state", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("coalesces rapid cross-page scrolling into the final rows query", async () => {
    vi.useFakeTimers();
    const reloadData = vi.fn(async () => undefined);
    const loadRows = vi.fn<ScSampleTableDataSource["loadRows"]>(async (query) => ({
      items: [sampleRow(query.anchor ?? "0", 1)],
      total: 1_000,
      nextAnchor: null,
    }));
    const dataSource: ScSampleTableDataSource = { scopeKey: "dataset:one", loadRows };
    const { wrapper } = await mountWithProviders(ScSampleTableVxe, {
      props: { dataSource, pageSize: 10 },
      global: { stubs: tableStubs(reloadData) },
    });

    await vi.waitFor(() => expect(loadRows).toHaveBeenCalledTimes(1));
    const rail = wrapper.find<HTMLElement>(".sst-vxe-virtual-rail");
    for (const page of [1, 2, 3]) {
      rail.element.scrollTop = page * 10 * 36;
      await rail.trigger("scroll");
    }

    await vi.advanceTimersByTimeAsync(SC_SCROLL_QUERY_DEBOUNCE_MS - 1);
    expect(loadRows).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    await vi.waitFor(() => expect(loadRows).toHaveBeenCalledTimes(2));
    expect(loadRows.mock.calls[1]?.[0]).toMatchObject({ anchor: "30", limit: 12 });

    wrapper.unmount();
  }, 15_000);

  it("aborts an in-flight page query as soon as scrolling targets another page", async () => {
    vi.useFakeTimers();
    const reloadData = vi.fn(async () => undefined);
    const loadRows = vi.fn<ScSampleTableDataSource["loadRows"]>(async (query) => {
      if (query.anchor === "10") {
        return await new Promise((_resolve, reject) => {
          const rejectAbort = () => reject(new DOMException("aborted", "AbortError"));
          if (query.signal?.aborted) rejectAbort();
          else query.signal?.addEventListener("abort", rejectAbort, { once: true });
        });
      }
      return {
        items: [sampleRow(query.anchor, 1)],
        total: 1_000,
        nextAnchor: null,
      };
    });
    const dataSource: ScSampleTableDataSource = { scopeKey: "dataset:one", loadRows };
    const { wrapper } = await mountWithProviders(ScSampleTableVxe, {
      props: { dataSource, pageSize: 10 },
      global: { stubs: tableStubs(reloadData) },
    });

    await vi.waitFor(() => expect(loadRows).toHaveBeenCalledTimes(1));
    const rail = wrapper.find<HTMLElement>(".sst-vxe-virtual-rail");
    rail.element.scrollTop = 10 * 36;
    await rail.trigger("scroll");
    await vi.advanceTimersByTimeAsync(SC_SCROLL_QUERY_DEBOUNCE_MS);
    await vi.waitFor(() => expect(loadRows).toHaveBeenCalledTimes(2));

    rail.element.scrollTop = 20 * 36;
    await rail.trigger("scroll");
    expect(loadRows.mock.calls[1]?.[0].signal?.aborted).toBe(true);
    await vi.advanceTimersByTimeAsync(SC_SCROLL_QUERY_DEBOUNCE_MS);
    await vi.waitFor(() => expect(loadRows).toHaveBeenCalledTimes(3));

    expect(loadRows.mock.calls[2]?.[0]).toMatchObject({ anchor: "20", limit: 12 });
    expect(wrapper.find(".sst-vxe-error").exists()).toBe(false);
    wrapper.unmount();
  }, 15_000);

  it("represents all filtered rows without resolving every defect ID", async () => {
    const reloadData = vi.fn(async () => undefined);
    const loadRows = vi.fn<ScSampleTableDataSource["loadRows"]>(async () => ({
      items: [sampleRow("11", 1), sampleRow("12", 1)],
      total: 300_000,
      nextAnchor: "2",
    }));
    const dataSource: ScSampleTableDataSource = { scopeKey: "dataset:one", loadRows };
    const { wrapper } = await mountWithProviders(ScSampleTableVxe, {
      props: { dataSource, enableSelection: true },
      global: { stubs: tableStubs(reloadData) },
    });

    await vi.waitFor(() => expect(loadRows).toHaveBeenCalledTimes(1));
    wrapper.findComponent({ name: "VxeTable" }).vm.$emit("checkbox-all", { checked: true });
    await vi.waitFor(() =>
      expect(wrapper.emitted("selection-change")).toEqual([[{ kind: "all", excludedIds: [] }]]),
    );
    expect(loadRows).toHaveBeenCalledTimes(1);

    wrapper.findComponent({ name: "VxeTable" }).vm.$emit("checkbox-change", {
      checked: false,
      row: sampleRow("11", 1),
    });
    await vi.waitFor(() =>
      expect(wrapper.emitted("selection-change")?.[1]).toEqual([
        { kind: "all", excludedIds: [11] },
      ]),
    );
  });

  it("reloads the first table page once when a header sort changes", async () => {
    const reloadData = vi.fn(async () => undefined);
    const loadRows = vi.fn<ScSampleTableDataSource["loadRows"]>(async (query) => {
      const rows =
        query.sort?.field === "images" && query.sort.direction === "asc"
          ? [sampleRow("2", 1), sampleRow("1", 2)]
          : [sampleRow("1", 2), sampleRow("2", 1)];
      return { items: rows, total: rows.length, nextAnchor: null };
    });
    const dataSource: ScSampleTableDataSource = { scopeKey: "dataset:one", loadRows };
    const { wrapper } = await mountWithProviders(ScSampleTableVxe, {
      props: { dataSource },
      global: { stubs: tableStubs(reloadData) },
    });

    await vi.waitFor(() => {
      expect(loadRows).toHaveBeenCalledTimes(1);
      expect(reloadData).toHaveBeenCalledTimes(1);
    });
    reloadData.mockClear();
    const sortButtons = wrapper.findAll(".sst-vxe-sort-button");
    expect(sortButtons).toHaveLength(20);
    await sortButtons[1]?.trigger("click");

    await vi.waitFor(() => expect(loadRows).toHaveBeenCalledTimes(2));
    expect(loadRows.mock.calls[1]?.[0].sort).toEqual({ field: "images", direction: "asc" });
    expect(reloadData).toHaveBeenCalledTimes(1);
    expect(reloadData.mock.calls[0]?.[0].map((row) => row.defect_id)).toEqual(["2", "1"]);

    await wrapper.setProps({ sort: { field: "images", direction: "asc" } });
    await new Promise((resolve) => setTimeout(resolve, 25));
    expect(loadRows).toHaveBeenCalledTimes(2);
  });

  it("reloads rows when an externally controlled table filter changes", async () => {
    const reloadData = vi.fn(async () => undefined);
    const loadRows = vi.fn<ScSampleTableDataSource["loadRows"]>(async (query) => ({
      items: [sampleRow("1", 2)],
      total: query.filter?.rough_bin ? 1 : 2,
      nextAnchor: null,
    }));
    const dataSource: ScSampleTableDataSource = { scopeKey: "dataset:one", loadRows };
    const { wrapper } = await mountWithProviders(ScSampleTableVxe, {
      props: { dataSource },
      global: { stubs: tableStubs(reloadData) },
    });

    await vi.waitFor(() => expect(loadRows).toHaveBeenCalledTimes(1));
    await wrapper.setProps({
      filter: { rough_bin: { filterType: "set", values: [7] } },
    });

    await vi.waitFor(() => expect(loadRows).toHaveBeenCalledTimes(2));
    expect(loadRows.mock.calls[1]?.[0].filter).toEqual({
      rough_bin: { filterType: "set", values: [7] },
    });
  });

  it("renders metadata columns discovered from the backend schema", async () => {
    const reloadData = vi.fn(async () => undefined);
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
    const { wrapper } = await mountWithProviders(ScSampleTableVxe, {
      props: { dataSource },
      global: { stubs: tableStubs(reloadData) },
    });

    await vi.waitFor(() => expect(wrapper.text()).toContain("future_metric"));
    expect(wrapper.findAll(".sst-vxe-sort-button")).toHaveLength(2);
  });
});
