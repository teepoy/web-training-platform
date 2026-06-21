import { describe, expect, it, vi } from "vitest";
import { effectScope, nextTick, ref } from "vue";
import { mockTanstackVirtual } from "@/testing/mocks/tanstack-virtual";
import { useBlinkVirtualScroll } from "./useBlinkVirtualScroll";
import type { ScSampleItem } from "@/features/sc/generated/proto/sc/v1/sample_pb";

mockTanstackVirtual();

describe("useBlinkVirtualScroll", () => {
  it("remeasures virtual rows when cell size changes", async () => {
    const scope = effectScope();
    const patchCellSize = ref(64);
    let measure: ReturnType<typeof vi.fn> | undefined;

    scope.run(() => {
      const { virtualizer } = useBlinkVirtualScroll({
        samples: ref([{ defectId: 1, reviewImages: [] }] as unknown as ScSampleItem[]),
        mode: ref("patch"),
        patchPerRow: ref(1),
        reviewPerRow: ref(1),
        patchCellSize,
      });
      measure = virtualizer.value.measure as ReturnType<typeof vi.fn>;
    });

    patchCellSize.value = 128;
    await nextTick();
    await nextTick();

    expect(measure).toHaveBeenCalled();
    scope.stop();
  });
});
