import { computed, effectScope, ref } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ScWorkbenchDataSource } from "@/features/sc/domain/workbenchDataSource";
import { SC_SCROLL_QUERY_DEBOUNCE_MS } from "./scrollQueryDebounce";
import { usePagedDataGallery } from "./usePagedDataGallery";

function createDataSource(): ScWorkbenchDataSource {
  return {
    scopeKey: "dataset:one",
    loadMap: vi.fn(async () => new Uint8Array()),
    loadRows: vi.fn(async () => ({ items: [], total: 0, nextAnchor: null })),
    loadGallery: vi.fn(async () => ({ ipc: new Uint8Array([1]), total: 100, nextOffset: 20 })),
    loadAggregates: vi.fn(async () => ({})),
    loadNumericRange: vi.fn(async () => null),
    loadDistinctValues: vi.fn(async () => []),
    resolveSelection: vi.fn(async () => []),
    subscribeInvalidations: vi.fn(() => () => undefined),
    close: vi.fn(),
  };
}

describe("usePagedDataGallery", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("coalesces rapid virtual-range changes into the final gallery query", async () => {
    vi.useFakeTimers();
    const source = createDataSource();
    const requestedRange = ref({ start: 0, end: 1 });
    const scope = effectScope();
    scope.run(() =>
      usePagedDataGallery(
        computed(() => source),
        computed(() => ({ mode: "patch" as const })),
        requestedRange,
        computed(() => true),
        () => [],
      ),
    );

    requestedRange.value = { start: 0, end: 8 };
    requestedRange.value = { start: 0, end: 24 };
    requestedRange.value = { start: 0, end: 40 };
    await vi.advanceTimersByTimeAsync(SC_SCROLL_QUERY_DEBOUNCE_MS - 1);
    expect(source.loadGallery).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    await vi.waitFor(() => expect(source.loadGallery).toHaveBeenCalledTimes(1));
    expect(source.loadGallery).toHaveBeenCalledWith({
      mode: "patch",
      offset: 0,
      limit: 40,
    });
    scope.stop();
  });

  it("reuses the loaded Arrow window when a new range is already covered", async () => {
    vi.useFakeTimers();
    const source = createDataSource();
    const requestedRange = ref({ start: 0, end: 100 });
    const scope = effectScope();
    scope.run(() =>
      usePagedDataGallery(
        computed(() => source),
        computed(() => ({ mode: "patch" as const })),
        requestedRange,
        computed(() => true),
        () => Array.from({ length: 100 }, (_, index) => index),
      ),
    );

    await vi.advanceTimersByTimeAsync(SC_SCROLL_QUERY_DEBOUNCE_MS);
    await vi.waitFor(() => expect(source.loadGallery).toHaveBeenCalledTimes(1));
    requestedRange.value = { start: 8, end: 40 };
    await vi.advanceTimersByTimeAsync(SC_SCROLL_QUERY_DEBOUNCE_MS);

    expect(source.loadGallery).toHaveBeenCalledTimes(1);
    scope.stop();
  });

  it("loads only while its gallery mode is active", async () => {
    vi.useFakeTimers();
    const source = createDataSource();
    const requestedRange = ref({ start: 0, end: 20 });
    const enabled = ref(false);
    const scope = effectScope();
    scope.run(() =>
      usePagedDataGallery(
        computed(() => source),
        computed(() => ({ mode: "review" as const })),
        requestedRange,
        computed(() => enabled.value),
        () => [],
      ),
    );

    await vi.advanceTimersByTimeAsync(SC_SCROLL_QUERY_DEBOUNCE_MS * 2);
    expect(source.loadGallery).not.toHaveBeenCalled();

    enabled.value = true;
    await vi.advanceTimersByTimeAsync(SC_SCROLL_QUERY_DEBOUNCE_MS);
    await vi.waitFor(() => expect(source.loadGallery).toHaveBeenCalledTimes(1));
    expect(source.loadGallery).toHaveBeenCalledWith({
      mode: "review",
      offset: 0,
      limit: 20,
    });

    enabled.value = false;
    requestedRange.value = { start: 20, end: 40 };
    await vi.advanceTimersByTimeAsync(SC_SCROLL_QUERY_DEBOUNCE_MS * 2);
    expect(source.loadGallery).toHaveBeenCalledTimes(1);
    scope.stop();
  });
});
