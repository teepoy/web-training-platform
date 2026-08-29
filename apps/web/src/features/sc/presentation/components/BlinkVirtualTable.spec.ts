import { tableFromArrays, tableToIPC } from "apache-arrow";
import { flushPromises } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import type { ScWorkbenchDataSource } from "@/features/sc/domain/workbenchDataSource";
import { mountWithProviders } from "@/testing";
import { mockTanstackVirtual } from "@/testing/mocks/tanstack-virtual";
import BlinkVirtualTable from "./BlinkVirtualTable.vue";

mockTanstackVirtual();

vi.mock("./scInspectionImageProfile", async () => {
  const actual = await vi.importActual<typeof import("./scInspectionImageProfile")>(
    "./scInspectionImageProfile",
  );
  return {
    ...actual,
    loadScInspectionImageProfile: vi.fn().mockResolvedValue({
      inspection_time: "2026-08-21T00:00:00Z",
      wafer_key: 1,
      reference_count: 2,
      difference_count: 2,
      mask_count: 1,
      patches: [
        { image_type: "Defective", image_id: null, bit_depth: 12, z_min: 100, z_max: 3500 },
        { image_type: "Reference", image_id: 0, bit_depth: 12, z_min: 200, z_max: 3000 },
        { image_type: "Reference", image_id: 1, bit_depth: 12, z_min: 300, z_max: 3200 },
        { image_type: "Difference", image_id: 0, bit_depth: 12, z_min: 10, z_max: 1000 },
        { image_type: "Difference", image_id: 1, bit_depth: 12, z_min: 20, z_max: 2000 },
        { image_type: "Mask", image_id: 0, bit_depth: 8, z_min: 0, z_max: 1 },
      ],
    }),
  };
});

describe("BlinkVirtualTable gallery settings", () => {
  it("keeps Gallery and Colors as separate tabs and adapts to all patch instances", async () => {
    const { wrapper } = await mountWithProviders(BlinkVirtualTable, {
      props: {
        inspectionTime: "2026-08-21T00:00:00Z",
        waferKey: 1,
      },
    });
    expect(wrapper.find('[data-testid="gallery-color-dock"]').exists()).toBe(true);
    await flushPromises();
    const layoutTab = document.querySelector<HTMLElement>('[data-name="gallery"]');
    const colorTab = document.querySelector<HTMLElement>('[data-name="colors"]');
    expect(layoutTab?.textContent).toContain("Gallery");
    expect(colorTab?.textContent).toContain("Colors");
    expect(document.body.textContent).toContain("Reference 1");
    expect(document.body.textContent).toContain("Reference 2");
    expect(document.body.textContent).toContain("Difference 2");
    colorTab?.click();
    await wrapper.vm.$nextTick();
    expect(document.body.textContent).toContain("D / R");
    expect(document.body.textContent).toContain("Difference");
    expect(document.querySelector('[data-testid="gallery-gray-mapping-toggle"]')).not.toBeNull();
  });

  it("returns the viewport to the first row when filters change", async () => {
    const ipc = tableToIPC(tableFromArrays({ row_key: ["1"], defect_id: [1] }));
    const source: ScWorkbenchDataSource = {
      scopeKey: "dataset:filtered",
      loadColumns: vi.fn(async () => []),
      loadMap: vi.fn(async () => new Uint8Array()),
      loadRows: vi.fn(async () => ({ items: [], total: 0, nextAnchor: null })),
      loadGallery: vi.fn(async () => ({ ipc, total: 100, nextOffset: 1 })),
      loadAggregates: vi.fn(async () => ({})),
      loadNumericRange: vi.fn(async () => null),
      loadDistinctValues: vi.fn(async () => []),
      resolveSelection: vi.fn(async () => []),
      subscribeInvalidations: vi.fn(() => () => undefined),
      close: vi.fn(),
    };
    const { wrapper } = await mountWithProviders(BlinkVirtualTable, {
      props: {
        inspectionTime: "2026-08-21T00:00:00Z",
        waferKey: 1,
        dataSource: source,
        galleryQuery: { filters: [] },
      },
    });
    await vi.waitFor(() => expect(source.loadGallery).toHaveBeenCalled());
    const scroll = wrapper.get(".sbt-scroll").element as HTMLElement;
    scroll.scrollTop = 640;

    await wrapper.setProps({ galleryQuery: { filters: [["class_number", "=", 1]] } });
    await flushPromises();

    expect(scroll.scrollTop).toBe(0);
  });
});
