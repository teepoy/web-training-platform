import { describe, it, expect, vi, beforeEach } from "vitest";
import { mountWithProviders } from "@/testing";
import PerspectiveInspectionQuad from "../PerspectiveInspectionQuad.vue";

// Mock heavy child components
vi.mock("../ScMapPanelBinned.vue", () => ({
  default: {
    name: "ScMapPanelBinned",
    props: { highlightDefects: Array },
    template: "<div />",
  },
}));
vi.mock("../ScGlobalFilterBar.vue", () => ({
  default: { name: "ScGlobalFilterBar", template: "<div />" },
}));
vi.mock("../ScSampleTable.vue", () => ({
  default: { name: "ScSampleTable", template: "<div />" },
}));
vi.mock("../ScPreviewBlinkVirtualTable.vue", () => ({
  default: { name: "ScPreviewBlinkVirtualTable", template: "<div />" },
}));
// Mock Perspective workbench
vi.mock("@/features/sc/presentation/composables/useScPerspectiveWorkbench", () => ({
  useScPerspectiveWorkbench: () => ({
    table: { value: null },
    connected: { value: false },
    error: { value: null },
    connect: vi.fn(),
    disconnect: vi.fn(),
  }),
}));

describe("PerspectiveInspectionQuad — highlight watcher", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it("sets highlightDefects to empty when > 9999 gallery selected", async () => {
    const largeIds = Array.from({ length: 10000 }, (_, i) => i + 1);
    const { wrapper } = await mountWithProviders(PerspectiveInspectionQuad, {
      props: {
        variant: "preview",
        samples: [],
        samplesLoading: false,
        samplesError: null,
        activeMapTab: "wafer",
        gallerySelectedDefectIds: largeIds,
      },
    });
    await vi.runAllTimersAsync();
    const mapPanel = wrapper.findComponent({ name: "ScMapPanelBinned" });
    expect(mapPanel.props("highlightDefects")).toEqual([]);
  });

  it("calls model when ≤ 9999 selected (debounced)", async () => {
    const { wrapper } = await mountWithProviders(PerspectiveInspectionQuad, {
      props: {
        variant: "preview",
        samples: [],
        samplesLoading: false,
        samplesError: null,
        activeMapTab: "wafer",
        gallerySelectedDefectIds: [1, 2, 3],
      },
    });
    await vi.runAllTimersAsync();
    // Just verify no crash — model.highlightDefectsForIds would be called in real app
    const mapPanel = wrapper.findComponent({ name: "ScMapPanelBinned" });
    expect(mapPanel.exists()).toBe(true);
  });
});
