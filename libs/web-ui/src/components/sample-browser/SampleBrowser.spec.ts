import { describe, it, expect, vi, beforeAll } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";

// ---------------------------------------------------------------------------
// Mocks — MUST be imported/defined before the component
// ---------------------------------------------------------------------------

vi.mock("@tanstack/vue-virtual", () => ({
  useVirtualizer: (options: {
    count: (() => number) | number;
    estimateSize: (() => number) | number;
  }) => {
    const count =
      typeof options.count === "function" ? options.count() : options.count;
    const size =
      typeof options.estimateSize === "function"
        ? options.estimateSize()
        : options.estimateSize;

    const inner = {
      getVirtualItems: () =>
        Array.from({ length: count }, (_, i) => ({
          index: i,
          size,
          start: i * size,
        })),
      getTotalSize: () => count * size,
      measure: vi.fn(),
      scrollToIndex: vi.fn(),
    };

    // Wrapper: .value for script watchers, direct access for template unwrap
    return {
      value: inner,
      getVirtualItems: inner.getVirtualItems,
      getTotalSize: inner.getTotalSize,
      measure: inner.measure,
      scrollToIndex: inner.scrollToIndex,
    };
  },
}));

// ResizeObserver is not available in jsdom
class MockResizeObserver {
  observe = vi.fn();
  disconnect = vi.fn();
  unobserve = vi.fn();
}

// ---------------------------------------------------------------------------

import SampleBrowser from "./SampleBrowser.vue";
import type { BrowserItem } from "../../types/components";

const browserItems: BrowserItem[] = Array.from({ length: 20 }, (_, i) => ({
  id: `item-${String(i).padStart(3, "0")}`,
  imageSrcs: [`https://picsum.photos/160/160?random=${i}`],
  metadata: { filename: `sample_${i}.jpg`, index: i },
  currentLabel: i % 3 === 0 ? "cat" : i % 3 === 1 ? "dog" : null,
  draftLabel: i % 5 === 0 ? "bird" : null,
  predictionLabel: i % 2 === 0 ? "cat" : "dog",
  predictionConfidence: Math.random() * 0.5 + 0.5,
  predictionId: `pred-${i}`,
  sourceKind: "dataset" as const,
  activationLabel: null,
}));

function mountBrowser(props?: Record<string, unknown>, attachTo?: HTMLElement) {
  return mount(SampleBrowser, {
    props: {
      items: browserItems,
      totalCount: 20,
      ...props,
    },
    attachTo,
  });
}

describe("SampleBrowser", () => {
  beforeAll(() => {
    vi.stubGlobal("ResizeObserver", MockResizeObserver);
  });

  // -----------------------------------------------------------------------
  // 1. Grid renders
  // -----------------------------------------------------------------------
  it("renders grid layout with virtualized items", async () => {
    const container = document.createElement("div");
    container.style.height = "600px";
    container.style.width = "900px";

    const wrapper = mountBrowser({ layout: "grid" }, container);
    await nextTick();

    expect(wrapper.find(".sb").exists()).toBe(true);
    expect(wrapper.find(".sb-card-row").exists()).toBe(true);
    const firstCard = wrapper.find('[data-sb-id="item-000"]');
    expect(firstCard.exists()).toBe(true);
    expect(wrapper.text()).toContain("cat");
  });

  // -----------------------------------------------------------------------
  // 2. List mode
  // -----------------------------------------------------------------------
  it("renders list layout when layout is list", async () => {
    const container = document.createElement("div");
    container.style.height = "600px";
    container.style.width = "900px";

    const wrapper = mountBrowser({ layout: "list" }, container);
    await nextTick();

    expect(wrapper.find(".sb-list-row").exists()).toBe(true);
    expect(wrapper.find(".sb-card-row").exists()).toBe(false);
    expect(wrapper.text()).toContain("item-000");
    expect(wrapper.text()).toContain("sample_0.jpg");
  });

  // -----------------------------------------------------------------------
  // 3. Selection emit
  // -----------------------------------------------------------------------
  it("emits select event when item is clicked with selection enabled", async () => {
    const container = document.createElement("div");
    container.style.height = "600px";
    container.style.width = "900px";

    const wrapper = mountBrowser(
      { selectionEnabled: true, activationMode: "select" },
      container,
    );
    await nextTick();

    const firstItem = wrapper.find('[data-sb-id="item-000"]');
    expect(firstItem.exists()).toBe(true);
    await firstItem.trigger("click");

    const emitted = wrapper.emitted("select");
    expect(emitted).toBeTruthy();
    expect(emitted!.length).toBeGreaterThanOrEqual(1);
    const lastCall = emitted![emitted!.length - 1];
    expect(lastCall[0]).toBeInstanceOf(Set);
    expect((lastCall[0] as Set<string>).has("item-000")).toBe(true);
  });

  // -----------------------------------------------------------------------
  // 4. Loading indicator
  // -----------------------------------------------------------------------
  it("shows loading indicator when isLoading is true", async () => {
    const container = document.createElement("div");
    container.style.height = "600px";
    container.style.width = "900px";

    const wrapper = mountBrowser({ isLoading: true }, container);
    await nextTick();

    expect(wrapper.find(".sb-loading").exists()).toBe(true);
    expect(wrapper.find(".sb-loading").text()).toBe("Loading more...");
  });

  // -----------------------------------------------------------------------
  // 5. Empty state
  // -----------------------------------------------------------------------
  it("renders empty state when items array is empty", async () => {
    const container = document.createElement("div");
    container.style.height = "600px";
    container.style.width = "900px";

    const wrapper = mountBrowser({ items: [], totalCount: 0 }, container);
    await nextTick();

    expect(wrapper.find(".sb").exists()).toBe(true);
    expect(wrapper.find(".sb-card-row").exists()).toBe(false);
    expect(wrapper.find(".sb-list-row").exists()).toBe(false);
    expect(wrapper.findAll('[data-sb-id]').length).toBe(0);
  });
});
