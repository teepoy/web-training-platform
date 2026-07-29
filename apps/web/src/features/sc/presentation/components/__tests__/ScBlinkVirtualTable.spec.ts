import { tableFromArrays, tableToIPC } from "apache-arrow";
import { describe, it, expect, vi } from "vitest";
import { mountWithProviders } from "@/testing";
import type { PerspectiveViewSnapshot } from "../composables/useManagedPerspectiveView";
import ScBlinkVirtualTable from "../ScBlinkVirtualTable.vue";

describe("ScBlinkVirtualTable - loading", () => {
  it("shows loading status when loading is true", async () => {
    const { wrapper } = await mountWithProviders(ScBlinkVirtualTable, {
      props: { loading: true },
    });
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("Loading...");
  });

  it("hides loading status when loading is false", async () => {
    const { wrapper } = await mountWithProviders(ScBlinkVirtualTable, {
      props: { loading: false },
    });
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).not.toContain("Loading...");
  });

  it("loads only an Arrow window while reporting the full gallery size", async () => {
    const total = 300_000;
    const toArrow = vi.fn(async (options: { start_row: number; end_row: number }) =>
      tableToIPC(
        tableFromArrays({
          defect_id: Array.from(
            { length: options.end_row - options.start_row },
            (_, index) => options.start_row + index + 1,
          ),
        }),
      ),
    );
    const rawView = {};
    const snapshot = {
      viewConfigKey: "patch-gallery",
      view: {
        rawView,
        num_rows: vi.fn(async () => total),
        to_arrow: toArrow,
      },
    } as unknown as PerspectiveViewSnapshot;

    const { wrapper } = await mountWithProviders(ScBlinkVirtualTable, {
      props: {
        inspectionTime: "2026-07-26T04:00:00+08:00",
        waferKey: 1,
        patchViewSnapshot: snapshot,
      },
    });

    await vi.waitFor(() => {
      expect(wrapper.attributes("data-total-samples")).toBe(String(total));
      expect(wrapper.attributes("data-loaded-samples")).toBe("2000");
    });
    expect(wrapper.attributes("data-sample-offset")).toBe("0");
    expect(wrapper.text()).toContain("300,000 samples");
    expect(toArrow).toHaveBeenCalledWith({
      start_row: 0,
      end_row: 2_000,
    });
  });

  it("does not reload gallery data when selection highlighting is cleared", async () => {
    const toArrow = vi.fn(async () =>
      tableToIPC(
        tableFromArrays({
          defect_id: [1, 2, 3],
        }),
      ),
    );
    const snapshot = {
      viewConfigKey: "patch-gallery",
      view: {
        rawView: {},
        num_rows: vi.fn(async () => 3),
        to_arrow: toArrow,
      },
    } as unknown as PerspectiveViewSnapshot;
    const { wrapper } = await mountWithProviders(ScBlinkVirtualTable, {
      props: {
        inspectionTime: "2026-07-26T04:00:00+08:00",
        patchViewSnapshot: snapshot,
        selectedDefectIds: new Set(["1"]),
        waferKey: 1,
      },
    });
    await vi.waitFor(() => {
      expect(wrapper.attributes("data-loaded-samples")).toBe("3");
    });
    toArrow.mockClear();

    await wrapper.setProps({ selectedDefectIds: new Set<string>() });
    await wrapper.vm.$nextTick();

    expect(toArrow).not.toHaveBeenCalled();
    expect(wrapper.text()).not.toContain("Loading...");
  });
});
