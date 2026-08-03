import { tableFromArrays, tableToIPC } from "apache-arrow";
import type { Table, View } from "@perspective-dev/client";
import { defineComponent } from "vue";
import { describe, expect, it, vi } from "vitest";
import { mountWithProviders } from "@/testing";
import ScSampleTableVxe from "./ScSampleTableVxe.vue";

function ipc(columns: Record<string, Array<number | string>>): Uint8Array {
  return tableToIPC(tableFromArrays(columns));
}

describe("ScSampleTableVxe virtual paging", () => {
  it("maps wheel movement to VXE page-local scrolling and loads crossed pages", async () => {
    const total = 2_000;
    const defectIds = Array.from({ length: total }, (_, index) => index + 1);
    const scrollTo = vi.fn(async () => undefined);
    const view = {
      num_rows: vi.fn(async () => total),
      column_paths: vi.fn(async () => ["defect_id", "images"]),
      to_arrow: vi.fn(
        async (options: {
          start_row?: number;
          end_row?: number;
          start_col?: number;
          end_col?: number;
        }) => {
          if (options.start_col !== undefined) {
            return ipc({ defect_id: defectIds });
          }
          const start = options.start_row ?? 0;
          const end = options.end_row ?? total;
          return ipc({
            defect_id: defectIds.slice(start, end),
            images: Array.from({ length: end - start }, () => 5),
          });
        },
      ),
      on_update: vi.fn(),
      delete: vi.fn(async () => undefined),
    } as unknown as View;
    const table = {
      view: vi.fn(async () => view),
    } as unknown as Table;
    const VxeTableStub = defineComponent({
      name: "VxeTable",
      setup(_props, { expose }) {
        expose({
          clearCheckboxRow: vi.fn(),
          getScrollData: vi.fn(() => ({
            clientWidth: 400,
            scrollLeft: 640,
            scrollWidth: 2_400,
          })),
          loadData: vi.fn(async () => undefined),
          recalculate: vi.fn(async () => undefined),
          refreshScroll: vi.fn(async () => undefined),
          reloadData: vi.fn(async () => undefined),
          scrollTo,
          setCheckboxRowKey: vi.fn(),
        });
        return {};
      },
      template: '<div class="vxe-table-stub" />',
    });
    const { wrapper } = await mountWithProviders(ScSampleTableVxe, {
      props: {
        perspectiveTable: table,
        baseViewConfig: {},
      },
      global: {
        stubs: {
          "vxe-table": VxeTableStub,
          "vxe-column": true,
        },
      },
    });

    await vi.waitFor(() => {
      expect(wrapper.attributes("data-hydrated-rows")).toBe("250");
    });
    scrollTo.mockClear();

    expect(wrapper.get(".sst-vxe-scrollbar-rail--x").attributes("role")).toBe("scrollbar");
    expect(wrapper.get(".sst-vxe-scrollbar-rail--y").attributes("role")).toBe("scrollbar");
    expect(wrapper.findAll(".sst-vxe-scrollbar-thumb")).toHaveLength(2);

    const rail = wrapper.get(".sst-vxe-virtual-rail");
    Object.defineProperties(rail.element, {
      clientHeight: { configurable: true, value: 200 },
      scrollHeight: { configurable: true, value: total * 36 },
    });

    await wrapper.get(".sst-vxe").trigger("wheel", {
      deltaX: 0,
      deltaY: 120,
      deltaMode: 0,
    });
    expect(rail.element.scrollTop).toBe(120);
    await rail.trigger("scroll");
    await vi.waitFor(() => {
      expect(scrollTo).toHaveBeenCalledWith(null, 120);
    });

    rail.element.scrollTop = 13_500;
    await rail.trigger("scroll");
    await vi.waitFor(() => {
      expect(view.to_arrow).toHaveBeenCalledWith({
        start_row: 250,
        end_row: 500,
      });
      expect(scrollTo).toHaveBeenCalledWith(null, 4_500);
      expect(scrollTo).toHaveBeenCalledWith(640, null);
    });

    expect(wrapper.attributes("data-hydrated-rows")).toBe("250");
    expect(wrapper.attributes("data-row-objects")).toBe("250");
    wrapper.unmount();
  });

  it("selects every defect id from the Arrow vector, not only the hydrated page", async () => {
    const total = 2_000;
    const defectIds = Array.from({ length: total }, (_, index) => index + 1);
    let onViewUpdate: ((event: { port_id?: number }) => void) | undefined;
    const view = {
      num_rows: vi.fn(async () => total),
      column_paths: vi.fn(async () => ["defect_id", "images"]),
      to_arrow: vi.fn(
        async (options: {
          start_row?: number;
          end_row?: number;
          start_col?: number;
          end_col?: number;
        }) => {
          if (options.start_col !== undefined) {
            return ipc({ defect_id: defectIds });
          }
          const start = options.start_row ?? 0;
          const end = options.end_row ?? total;
          return ipc({
            defect_id: defectIds.slice(start, end),
            images: Array.from({ length: end - start }, () => 5),
          });
        },
      ),
      on_update: vi.fn((callback: (event: { port_id?: number }) => void) => {
        onViewUpdate = callback;
      }),
      delete: vi.fn(async () => undefined),
    } as unknown as View;
    const table = {
      view: vi.fn(async () => view),
    } as unknown as Table;
    const VxeTableStub = defineComponent({
      name: "VxeTable",
      emits: ["checkbox-all"],
      setup(_props, { emit, expose }) {
        expose({
          clearCheckboxRow: vi.fn(),
          getScrollData: vi.fn(() => ({
            clientWidth: 400,
            scrollLeft: 0,
            scrollWidth: 2_400,
          })),
          loadData: vi.fn(async () => undefined),
          recalculate: vi.fn(async () => undefined),
          refreshScroll: vi.fn(async () => undefined),
          reloadData: vi.fn(async () => undefined),
          scrollTo: vi.fn(async () => undefined),
          setCheckboxRowKey: vi.fn(),
        });
        return {
          selectAll: () => emit("checkbox-all", { checked: true }),
          clearAll: () => emit("checkbox-all", { checked: false }),
        };
      },
      template:
        '<button class="select-all" @click="selectAll">all</button><button class="clear-all" @click="clearAll">none</button>',
    });
    const { wrapper } = await mountWithProviders(ScSampleTableVxe, {
      props: {
        perspectiveTable: table,
        baseViewConfig: {},
        enableSelection: true,
        ignoredPerspectiveUpdatePortIds: [77],
      },
      global: {
        stubs: {
          "vxe-table": VxeTableStub,
          "vxe-column": true,
        },
      },
    });

    await vi.waitFor(() => {
      expect(wrapper.attributes("data-hydrated-rows")).toBe("250");
    });
    expect(table.view).toHaveBeenCalledWith(
      expect.objectContaining({
        columns: expect.arrayContaining(["defect_id", "images"]),
      }),
    );
    const projectedColumns = (table.view as ReturnType<typeof vi.fn>).mock.calls[0]?.[0]
      ?.columns as string[];
    expect(projectedColumns).not.toContain("table_in_selection");

    const rowFetchCount = view.to_arrow.mock.calls.filter(
      ([options]) => options.start_col === undefined,
    ).length;
    onViewUpdate?.({ port_id: 77 });
    await new Promise((resolve) => setTimeout(resolve, 150));
    expect(
      view.to_arrow.mock.calls.filter(([options]) => options.start_col === undefined),
    ).toHaveLength(rowFetchCount);

    await wrapper.get(".select-all").trigger("click");

    const selected = wrapper.emitted("selection-change")?.at(-1)?.[0] as number[];
    expect(selected).toHaveLength(total);
    expect(selected[0]).toBe(1);
    expect(selected.at(-1)).toBe(total);
    expect(wrapper.attributes("data-row-objects")).toBe("250");

    await wrapper.get(".clear-all").trigger("click");
    expect(wrapper.emitted("selection-change")?.at(-1)?.[0]).toEqual([]);
    wrapper.unmount();
  });

  it("reloads table rows for repeated map-selection port updates", async () => {
    let defectIds = [1, 2];
    let onViewUpdate: ((event: { port_id?: number }) => void) | undefined;
    const reloadData = vi.fn(async () => undefined);
    const view = {
      num_rows: vi.fn(async () => defectIds.length),
      column_paths: vi.fn(async () => ["defect_id", "images"]),
      to_arrow: vi.fn(
        async (options: {
          start_row?: number;
          end_row?: number;
          start_col?: number;
          end_col?: number;
        }) => {
          if (options.start_col !== undefined) return ipc({ defect_id: defectIds });
          const start = options.start_row ?? 0;
          const end = Math.min(options.end_row ?? defectIds.length, defectIds.length);
          return ipc({
            defect_id: defectIds.slice(start, end),
            images: Array.from({ length: end - start }, () => 5),
          });
        },
      ),
      on_update: vi.fn((callback: (event: { port_id?: number }) => void) => {
        onViewUpdate = callback;
      }),
      delete: vi.fn(async () => undefined),
    } as unknown as View;
    const table = {
      view: vi.fn(async () => view),
    } as unknown as Table;
    const VxeTableStub = defineComponent({
      name: "VxeTable",
      setup(_props, { expose }) {
        expose({
          clearCheckboxRow: vi.fn(),
          getScrollData: vi.fn(() => ({
            clientWidth: 400,
            scrollLeft: 0,
            scrollWidth: 2_400,
          })),
          loadData: vi.fn(async () => undefined),
          recalculate: vi.fn(async () => undefined),
          refreshScroll: vi.fn(async () => undefined),
          reloadData,
          scrollTo: vi.fn(async () => undefined),
          setCheckboxRowKey: vi.fn(),
        });
        return {};
      },
      template: '<div class="vxe-table-stub" />',
    });
    const { wrapper } = await mountWithProviders(ScSampleTableVxe, {
      props: {
        perspectiveTable: table,
        baseViewConfig: {
          filter: [["map_in_selection", "==", 1]],
        },
        ignoredPerspectiveUpdatePortIds: [2],
      },
      global: {
        stubs: {
          "vxe-table": VxeTableStub,
          "vxe-column": true,
        },
      },
    });

    await vi.waitFor(() => {
      expect(wrapper.get(".sst-vxe-header-label").text()).toContain("2");
    });
    expect(reloadData).toHaveBeenCalledTimes(1);
    expect(reloadData.mock.calls[0]?.[0].map((row) => row.defect_id)).toEqual(["1", "2"]);

    defectIds = [99];
    onViewUpdate?.({ port_id: 2 });
    await new Promise((resolve) => setTimeout(resolve, 150));
    expect(reloadData).toHaveBeenCalledTimes(1);

    defectIds = [7, 8, 9];
    onViewUpdate?.({ port_id: 1 });
    await vi.waitFor(() => {
      expect(wrapper.get(".sst-vxe-header-label").text()).toContain("3");
      expect(reloadData).toHaveBeenCalledTimes(2);
    });
    expect(reloadData.mock.calls[1]?.[0].map((row) => row.defect_id)).toEqual(["7", "8", "9"]);

    defectIds = [10, 11, 12, 13];
    onViewUpdate?.({ port_id: 1 });
    await vi.waitFor(() => {
      expect(wrapper.get(".sst-vxe-header-label").text()).toContain("4");
      expect(reloadData).toHaveBeenCalledTimes(3);
    });
    expect(reloadData.mock.calls[2]?.[0].map((row) => row.defect_id)).toEqual([
      "10",
      "11",
      "12",
      "13",
    ]);

    wrapper.unmount();
  });

  it("rebuilds selected and all-sample views across repeated select and clear cycles", async () => {
    const selectedIds = [1, 2];
    const allIds = [1, 2, 3, 4];
    const views: Array<View & { delete: ReturnType<typeof vi.fn> }> = [];
    const table = {
      view: vi.fn(async (config: { filter?: unknown[] }) => {
        const filtered = config.filter?.some(
          (filter) =>
            Array.isArray(filter) &&
            filter[0] === "map_in_selection" &&
            filter[1] === "==" &&
            filter[2] === 1,
        );
        const defectIds = filtered ? selectedIds : allIds;
        const view = {
          num_rows: vi.fn(async () => defectIds.length),
          column_paths: vi.fn(async () => ["defect_id", "images"]),
          to_arrow: vi.fn(
            async (options: {
              start_row?: number;
              end_row?: number;
              start_col?: number;
              end_col?: number;
            }) => {
              if (options.start_col !== undefined) return ipc({ defect_id: defectIds });
              const start = options.start_row ?? 0;
              const end = Math.min(options.end_row ?? defectIds.length, defectIds.length);
              return ipc({
                defect_id: defectIds.slice(start, end),
                images: Array.from({ length: end - start }, () => 5),
              });
            },
          ),
          on_update: vi.fn(),
          delete: vi.fn(async () => undefined),
        } as unknown as View & { delete: ReturnType<typeof vi.fn> };
        views.push(view);
        return view;
      }),
    } as unknown as Table;
    const reloadData = vi.fn(async () => undefined);
    const VxeTableStub = defineComponent({
      name: "VxeTable",
      setup(_props, { expose }) {
        expose({
          clearCheckboxRow: vi.fn(),
          getScrollData: vi.fn(() => ({
            clientWidth: 400,
            scrollLeft: 0,
            scrollWidth: 2_400,
          })),
          loadData: vi.fn(async () => undefined),
          recalculate: vi.fn(async () => undefined),
          refreshScroll: vi.fn(async () => undefined),
          reloadData,
          scrollTo: vi.fn(async () => undefined),
          setCheckboxRowKey: vi.fn(),
        });
        return {};
      },
      template: '<div class="vxe-table-stub" />',
    });
    const { wrapper } = await mountWithProviders(ScSampleTableVxe, {
      props: {
        perspectiveTable: table,
        baseViewConfig: {
          filter: [["map_in_selection", "==", 1]],
        },
      },
      global: {
        stubs: {
          "vxe-table": VxeTableStub,
          "vxe-column": true,
        },
      },
    });

    await vi.waitFor(() => {
      expect(wrapper.get(".sst-vxe-header-label").text()).toContain("2");
    });

    await wrapper.setProps({ baseViewConfig: {} });
    await vi.waitFor(() => {
      expect(wrapper.get(".sst-vxe-header-label").text()).toContain("4");
      expect(table.view).toHaveBeenCalledTimes(2);
    });

    await wrapper.setProps({
      baseViewConfig: { filter: [["map_in_selection", "==", 1]] },
    });
    await vi.waitFor(() => {
      expect(wrapper.get(".sst-vxe-header-label").text()).toContain("2");
      expect(table.view).toHaveBeenCalledTimes(3);
    });

    await wrapper.setProps({ baseViewConfig: {} });
    await vi.waitFor(() => {
      expect(wrapper.get(".sst-vxe-header-label").text()).toContain("4");
      expect(table.view).toHaveBeenCalledTimes(4);
    });

    expect(reloadData.mock.calls.map(([rows]) => rows.map((row) => row.defect_id))).toEqual([
      ["1", "2"],
      ["1", "2", "3", "4"],
      ["1", "2"],
      ["1", "2", "3", "4"],
    ]);
    expect(views.slice(0, -1).every((view) => view.delete.mock.calls.length === 1)).toBe(true);
    wrapper.unmount();
  });

  it("invalidates the active page once for one header sort action", async () => {
    const defectIds = [1, 2, 3];
    const views: Array<View & { delete: ReturnType<typeof vi.fn> }> = [];
    const table = {
      view: vi.fn(async () => {
        const view = {
          num_rows: vi.fn(async () => defectIds.length),
          column_paths: vi.fn(async () => ["defect_id", "images"]),
          to_arrow: vi.fn(
            async (options: {
              start_row?: number;
              end_row?: number;
              start_col?: number;
              end_col?: number;
            }) => {
              if (options.start_col !== undefined) return ipc({ defect_id: defectIds });
              const start = options.start_row ?? 0;
              const end = options.end_row ?? defectIds.length;
              return ipc({
                defect_id: defectIds.slice(start, end),
                images: Array.from({ length: end - start }, () => 5),
              });
            },
          ),
          on_update: vi.fn(),
          delete: vi.fn(async () => undefined),
        } as unknown as View & { delete: ReturnType<typeof vi.fn> };
        views.push(view);
        return view;
      }),
    } as unknown as Table;
    const scrollTo = vi.fn(async () => undefined);
    const loadData = vi.fn(async () => undefined);
    const reloadData = vi.fn(async () => undefined);
    const VxeTableStub = defineComponent({
      name: "VxeTable",
      setup(_props, { expose }) {
        expose({
          clearCheckboxRow: vi.fn(),
          getScrollData: vi.fn(() => ({
            clientWidth: 400,
            scrollLeft: 640,
            scrollWidth: 2_400,
          })),
          loadData,
          recalculate: vi.fn(async () => undefined),
          refreshScroll: vi.fn(async () => undefined),
          reloadData,
          scrollTo,
          setCheckboxRowKey: vi.fn(),
        });
        return {};
      },
      template: '<div class="vxe-table-stub"><slot /></div>',
    });
    const VxeColumnStub = defineComponent({
      name: "VxeColumn",
      inheritAttrs: false,
      setup(_props, { slots }) {
        return () => slots.header?.();
      },
    });
    const { wrapper } = await mountWithProviders(ScSampleTableVxe, {
      props: {
        perspectiveTable: table,
        baseViewConfig: {},
      },
      global: {
        stubs: {
          VxeTable: VxeTableStub,
          VxeColumn: VxeColumnStub,
        },
      },
    });

    await vi.waitFor(() => {
      expect(wrapper.attributes("data-hydrated-rows")).toBe("3");
      expect(table.view).toHaveBeenCalledTimes(1);
    });
    loadData.mockClear();
    reloadData.mockClear();

    await wrapper.findAll(".sst-vxe-sort-button")[1]?.trigger("click");

    await vi.waitFor(() => {
      expect(wrapper.attributes("data-hydrated-rows")).toBe("3");
      expect(table.view).toHaveBeenCalledTimes(2);
    });
    await new Promise((resolve) => setTimeout(resolve, 25));
    expect(table.view).toHaveBeenCalledTimes(2);
    expect(views[0]?.delete).toHaveBeenCalledTimes(1);
    expect(loadData).not.toHaveBeenCalled();
    expect(reloadData).toHaveBeenCalledTimes(1);
    expect(reloadData.mock.calls[0]?.[0]).toHaveLength(3);
    expect(scrollTo).toHaveBeenCalledWith(640, null);

    const emittedSort = wrapper.emitted("sort-change")?.at(-1)?.[0];
    expect(emittedSort).toEqual({ field: "images", direction: "asc" });
    await wrapper.setProps({ sort: { field: "images", direction: "asc" } });
    await new Promise((resolve) => setTimeout(resolve, 25));
    expect(table.view).toHaveBeenCalledTimes(2);
    wrapper.unmount();
  });
});
