import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from "vitest";
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

import BlinkTable from "./BlinkTable.vue";
import BlinkImageCell from "./BlinkImageCell.vue";
import { blinkRows, extraColumns } from "./fixtures";

function mountBlinkTable(props?: Record<string, unknown>) {
  return mount(BlinkTable, {
    props: {
      rows: blinkRows,
      columns: extraColumns,
      ...props,
    },
  });
}

describe("BlinkTable", () => {
  beforeAll(() => {
    vi.stubGlobal("ResizeObserver", MockResizeObserver);
  });

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // -----------------------------------------------------------------------
  // 1. Default enabled rendering — blink column present
  // -----------------------------------------------------------------------
  it("renders with blink column when enabled (default)", async () => {
    const wrapper = mountBlinkTable();
    await nextTick();

    // Toolbar is present
    expect(wrapper.find(".bt").exists()).toBe(true);
    expect(wrapper.find(".bt-toolbar").exists()).toBe(true);

    // Blink header cell exists when enabled
    expect(wrapper.find(".bt-header-cell--image").exists()).toBe(true);

    // BlinkImageCell components are rendered (one per virtual row)
    expect(wrapper.findComponent(BlinkImageCell).exists()).toBe(true);
  });

  // -----------------------------------------------------------------------
  // 2. Disabled-mode — blink column structurally removed
  // -----------------------------------------------------------------------
  it("blink column is absent when initialBlinkEnabled is false", async () => {
    const wrapper = mountBlinkTable({ initialBlinkEnabled: false });
    await nextTick();

    // Image header cell must NOT exist
    expect(wrapper.find(".bt-header-cell--image").exists()).toBe(false);

    // No BlinkImageCell rendered
    expect(wrapper.findComponent(BlinkImageCell).exists()).toBe(false);

    // Data columns should still render
    expect(wrapper.find(".bt-header-cell").exists()).toBe(true);
  });

  // -----------------------------------------------------------------------
  // 3. All rows share the same phase (single global timer)
  // -----------------------------------------------------------------------
  it("all rows have same phase value — synchronized single timer", async () => {
    const wrapper = mountBlinkTable();
    await nextTick();

    // Advance 1 interval tick: phase A → B
    vi.advanceTimersByTime(1000);
    await nextTick();

    const imageCells = wrapper.findAllComponents(BlinkImageCell);
    expect(imageCells.length).toBe(10);

    // Every BlinkImageCell must receive phase "B"
    imageCells.forEach((cell) => {
      expect(cell.props("phase")).toBe("B");
    });
  });

  // -----------------------------------------------------------------------
  // 4. BlinkImageCell receives correct imageA / imageB props
  // -----------------------------------------------------------------------
  it("uses BlinkImageCell correctly with correct imageA/imageB props", async () => {
    const wrapper = mountBlinkTable();
    await nextTick();

    const cells = wrapper.findAllComponents(BlinkImageCell);
    expect(cells.length).toBe(10);

    // First row
    expect(cells[0].props("imageA")).toBe(blinkRows[0].imageA);
    expect(cells[0].props("imageB")).toBe(blinkRows[0].imageB);

    // Middle row
    expect(cells[5].props("imageA")).toBe(blinkRows[5].imageA);
    expect(cells[5].props("imageB")).toBe(blinkRows[5].imageB);

    // Last row
    expect(cells[9].props("imageA")).toBe(blinkRows[9].imageA);
    expect(cells[9].props("imageB")).toBe(blinkRows[9].imageB);
  });

  // -----------------------------------------------------------------------
  // 5. Empty state
  // -----------------------------------------------------------------------
  it("renders empty state when rows array is empty", async () => {
    const wrapper = mountBlinkTable({ rows: [], columns: extraColumns });
    await nextTick();

    expect(wrapper.find(".bt-empty").exists()).toBe(true);
    expect(wrapper.find(".bt-empty").text()).toBe("No rows to display");

    // No virtual rows rendered (no BlinkImageCell, no data cells)
    expect(wrapper.findComponent(BlinkImageCell).exists()).toBe(false);
    expect(wrapper.find(".bt-row").exists()).toBe(false);
  });

  // -----------------------------------------------------------------------
  // 6. Toggle switch removes / restores blink column
  // -----------------------------------------------------------------------
  it("toggle switch removes and restores blink column", async () => {
    const wrapper = mountBlinkTable();
    await nextTick();

    // Sanity: blink column is initially present
    expect(wrapper.findComponent(BlinkImageCell).exists()).toBe(true);
    expect(wrapper.find(".bt-header-cell--image").exists()).toBe(true);

    // Click the NSwitch toggle to disable blink
    const switchEl = wrapper.find(".n-switch");
    expect(switchEl.exists()).toBe(true);
    await switchEl.trigger("click");
    await nextTick();

    // Blink column should be structurally removed
    expect(wrapper.find(".bt-header-cell--image").exists()).toBe(false);
    expect(wrapper.findComponent(BlinkImageCell).exists()).toBe(false);

    // Click again to re-enable
    await switchEl.trigger("click");
    await nextTick();

    // Blink column should be back
    expect(wrapper.find(".bt-header-cell--image").exists()).toBe(true);
    expect(wrapper.findComponent(BlinkImageCell).exists()).toBe(true);
  });
});
