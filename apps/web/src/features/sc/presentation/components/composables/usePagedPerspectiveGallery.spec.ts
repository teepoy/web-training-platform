import { effectScope, ref } from "vue";
import { describe, expect, it, vi } from "vitest";
import type { PerspectiveViewSnapshot } from "./useManagedPerspectiveView";
import { usePagedPerspectiveGallery } from "./usePagedPerspectiveGallery";

function snapshotFor(total: number, toArrow: ReturnType<typeof vi.fn>): PerspectiveViewSnapshot {
  return {
    viewConfigKey: "gallery",
    view: {
      num_rows: vi.fn(async () => total),
      to_arrow: toArrow,
    },
  } as unknown as PerspectiveViewSnapshot;
}

describe("usePagedPerspectiveGallery", () => {
  it("keeps a two-page Arrow window and replaces it when scrolling crosses the range", async () => {
    const total = 300_000;
    const toArrow = vi.fn(async (options: unknown) => options);
    const snapshot = ref<PerspectiveViewSnapshot | null>(snapshotFor(total, toArrow));
    const requestedRange = ref({ start: 0, end: 40 });
    const parseItems = vi.fn((_ipc: unknown, offset: number) =>
      Array.from({ length: Math.min(2_000, total - offset) }, (_, index) => offset + index),
    );
    const scope = effectScope();
    const state = scope.run(() => usePagedPerspectiveGallery(snapshot, requestedRange, parseItems));

    await vi.waitFor(() => {
      expect(state?.window.value).toMatchObject({
        offset: 0,
        total,
      });
      expect(state?.window.value.items).toHaveLength(2_000);
    });
    expect(toArrow).toHaveBeenLastCalledWith({
      start_row: 0,
      end_row: 2_000,
    });

    requestedRange.value = { start: 1_990, end: 2_030 };
    await vi.waitFor(() => {
      expect(state?.window.value.offset).toBe(1_000);
      expect(state?.window.value.items[0]).toBe(1_000);
    });
    expect(toArrow).toHaveBeenLastCalledWith({
      start_row: 1_000,
      end_row: 3_000,
    });
    expect(state?.window.value.items).toHaveLength(2_000);

    scope.stop();
  });

  it("keeps the previous window visible until a refreshed snapshot is ready", async () => {
    let resolveRefresh: ((value: unknown) => void) | undefined;
    const firstToArrow = vi.fn(async () => "first");
    const refreshedToArrow = vi.fn(
      () =>
        new Promise((resolve) => {
          resolveRefresh = resolve;
        }),
    );
    const snapshot = ref<PerspectiveViewSnapshot | null>(snapshotFor(10, firstToArrow));
    const requestedRange = ref({ start: 0, end: 5 });
    const scope = effectScope();
    const state = scope.run(() =>
      usePagedPerspectiveGallery(snapshot, requestedRange, (ipc) => [String(ipc)]),
    );

    await vi.waitFor(() => {
      expect(state?.window.value.items).toEqual(["first"]);
    });

    snapshot.value = null;
    await vi.waitFor(() => {
      expect(state?.isPending.value).toBe(true);
    });
    expect(state?.window.value.items).toEqual(["first"]);

    snapshot.value = snapshotFor(10, refreshedToArrow);
    await vi.waitFor(() => {
      expect(refreshedToArrow).toHaveBeenCalledOnce();
    });
    await vi.waitFor(() => {
      expect(state?.isPending.value).toBe(true);
    });
    expect(state?.window.value.items).toEqual(["first"]);

    resolveRefresh?.("refreshed");
    await vi.waitFor(() => {
      expect(state?.window.value.items).toEqual(["refreshed"]);
      expect(state?.isPending.value).toBe(false);
    });

    scope.stop();
  });

  it("reloads the Blink window for repeated, mixed, and cleared map selections", async () => {
    const requestedRange = ref({ start: 0, end: 5 });
    const firstBox = vi.fn(async () => "box-1");
    const secondBox = vi.fn(async () => "box-2");
    const legend = vi.fn(async () => "legend");
    const allSamples = vi.fn(async () => "all");
    const snapshot = ref<PerspectiveViewSnapshot | null>(snapshotFor(2, firstBox));
    const scope = effectScope();
    const state = scope.run(() =>
      usePagedPerspectiveGallery(snapshot, requestedRange, (ipc) => [String(ipc)]),
    );

    await vi.waitFor(() => {
      expect(state?.window.value.items).toEqual(["box-1"]);
    });

    snapshot.value = snapshotFor(3, secondBox);
    await vi.waitFor(() => {
      expect(state?.window.value.items).toEqual(["box-2"]);
    });

    snapshot.value = snapshotFor(1, legend);
    await vi.waitFor(() => {
      expect(state?.window.value.items).toEqual(["legend"]);
    });

    snapshot.value = null;
    snapshot.value = snapshotFor(10, allSamples);
    await vi.waitFor(() => {
      expect(state?.window.value.items).toEqual(["all"]);
      expect(state?.window.value.total).toBe(10);
    });

    expect(firstBox).toHaveBeenCalledOnce();
    expect(secondBox).toHaveBeenCalledOnce();
    expect(legend).toHaveBeenCalledOnce();
    expect(allSamples).toHaveBeenCalledOnce();
    scope.stop();
  });
});
