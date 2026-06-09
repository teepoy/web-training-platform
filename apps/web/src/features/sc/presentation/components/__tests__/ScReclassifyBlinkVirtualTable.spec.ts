import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ref, defineComponent } from "vue";
import { mountWithProviders } from "@/testing";
import ScReclassifyBlinkVirtualTable from "../ScReclassifyBlinkVirtualTable.vue";

vi.mock("@/shared/components/blink-virtual-table", () => ({
  BlinkVirtualTableWithSelectionAndPreviewResultDisplay: defineComponent({
    name: "BlinkTableStub",
    setup(_, { expose }) {
      const scrollRef = ref<HTMLElement | null>(null);
      expose({ scrollRef });
      return { scrollRef };
    },
    template: '<div ref="scrollRef" class="sbt-scroll" style="height:100px;overflow:auto"><slot /></div>',
  }),
}));

type IntersectionCallback = (entries: IntersectionObserverEntry[]) => void;

let intersectionCallback: IntersectionCallback | null = null;
let intersectionObserverMock: { observe: ReturnType<typeof vi.fn>; unobserve: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn> };

beforeEach(() => {
  intersectionCallback = null;

  intersectionObserverMock = {
    observe: vi.fn(),
    unobserve: vi.fn(),
    disconnect: vi.fn(),
  };

  vi.stubGlobal("IntersectionObserver", vi.fn(function(this: unknown, cb: IntersectionCallback) {
    intersectionCallback = cb;
    return intersectionObserverMock;
  }));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function triggerIntersection(isIntersecting: boolean) {
  intersectionCallback?.([
    { isIntersecting } as unknown as IntersectionObserverEntry,
  ]);
}

const emptyProps = {
  samples: [],
  hasNextPage: false,
  isFetchingNextPage: false,
};

describe("ScReclassifyBlinkVirtualTable - spinner", () => {
  it("shows spinner when isFetchingNextPage is true", async () => {
    const { wrapper } = await mountWithProviders(ScReclassifyBlinkVirtualTable, {
      props: { ...emptyProps, isFetchingNextPage: true },
    });
    await wrapper.vm.$nextTick();
    expect(wrapper.find('[data-testid="reclassify-table-loadmore-spinner"]').exists()).toBe(true);
  });

  it("hides spinner when isFetchingNextPage is false", async () => {
    const { wrapper } = await mountWithProviders(ScReclassifyBlinkVirtualTable, {
      props: { ...emptyProps, isFetchingNextPage: false },
    });
    await wrapper.vm.$nextTick();
    expect(wrapper.find('[data-testid="reclassify-table-loadmore-spinner"]').exists()).toBe(false);
  });
});

describe("ScReclassifyBlinkVirtualTable - IntersectionObserver sentinel", () => {
  it("calls onLoadMore when sentinel becomes visible and hasNextPage is true", async () => {
    const onLoadMore = vi.fn();
    await mountWithProviders(ScReclassifyBlinkVirtualTable, {
      props: { ...emptyProps, hasNextPage: true, isFetchingNextPage: false, onLoadMore },
    });
    await new Promise((r) => setTimeout(r, 0));

    triggerIntersection(true);

    expect(onLoadMore).toHaveBeenCalledTimes(1);
  });

  it("does NOT call onLoadMore when hasNextPage is false", async () => {
    const onLoadMore = vi.fn();
    await mountWithProviders(ScReclassifyBlinkVirtualTable, {
      props: { ...emptyProps, hasNextPage: false, isFetchingNextPage: false, onLoadMore },
    });
    await new Promise((r) => setTimeout(r, 0));

    triggerIntersection(true);

    expect(onLoadMore).not.toHaveBeenCalled();
  });

  it("does NOT call onLoadMore again if isFetchingNextPage is true during intersection", async () => {
    const onLoadMore = vi.fn();
    await mountWithProviders(ScReclassifyBlinkVirtualTable, {
      props: { ...emptyProps, hasNextPage: true, isFetchingNextPage: true, onLoadMore },
    });
    await new Promise((r) => setTimeout(r, 0));

    triggerIntersection(true);

    expect(onLoadMore).not.toHaveBeenCalled();
  });

  it("does NOT call onLoadMore twice for the same intersection (no double-fire)", async () => {
    const onLoadMore = vi.fn();
    await mountWithProviders(ScReclassifyBlinkVirtualTable, {
      props: { ...emptyProps, hasNextPage: true, isFetchingNextPage: false, onLoadMore },
    });
    await new Promise((r) => setTimeout(r, 0));

    triggerIntersection(true);
    triggerIntersection(true);

    expect(onLoadMore).toHaveBeenCalledTimes(1);
  });
});
