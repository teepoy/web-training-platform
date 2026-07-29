import { defineComponent, h, ref } from "vue";
import { mount } from "@vue/test-utils";
import type { Table } from "@perspective-dev/client";
import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => {
  const toArrow = vi.fn(
    async ({ start_row: startRow }: { start_row: number; end_row: number }) =>
      new Uint8Array([startRow / 25_000]),
  );
  const retire = vi.fn();
  const view = {
    num_rows: vi.fn(async () => 300_000),
    to_arrow: toArrow,
    retire,
  };
  const createView = vi.fn(async () => view);
  return { createView, retire, toArrow, view };
});

vi.mock("@/features/sc/presentation/composables/managedPerspectiveView", () => ({
  managePerspectiveTable: () => ({ view: mocks.createView }),
}));

import { usePerspectiveMapView, type PerspectiveMapViewState } from "../usePerspectiveMapView";

describe("usePerspectiveMapView", () => {
  it("exports a large map as bounded Arrow chunks without the unused defect_id column", async () => {
    let state: PerspectiveMapViewState | undefined;
    const wrapper = mount(
      defineComponent({
        setup() {
          state = usePerspectiveMapView(
            ref({} as Table),
            ref([]),
            ref("class_number"),
            ref({ reticle_x: '"die_x"', reticle_y: '"die_y"' }),
          );
          return () => h("div");
        },
      }),
    );

    await vi.waitFor(() => {
      expect(state?.arrowData.value).toHaveLength(12);
    });
    expect(mocks.toArrow).toHaveBeenCalledTimes(12);
    expect(mocks.toArrow).toHaveBeenNthCalledWith(1, {
      start_row: 0,
      end_row: 25_000,
    });
    expect(mocks.toArrow).toHaveBeenLastCalledWith({
      start_row: 275_000,
      end_row: 300_000,
    });
    expect(mocks.createView).toHaveBeenCalledWith(
      expect.objectContaining({
        columns: expect.not.arrayContaining(["defect_id"]),
      }),
    );
    expect(mocks.retire).toHaveBeenCalledOnce();

    wrapper.unmount();
  });
});
