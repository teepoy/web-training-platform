import { describe, expect, it, vi } from "vitest";
import { effectScope, nextTick, ref } from "vue";
import { mockTanstackVirtual } from "@/testing/mocks/tanstack-virtual";
import { useBlinkVirtualScroll } from "./useBlinkVirtualScroll";

mockTanstackVirtual();

describe("useBlinkVirtualScroll", () => {
  it("remeasures virtual rows when cell size changes", async () => {
    const scope = effectScope();
    const patchCellSize = ref(64);
    let measure: ReturnType<typeof vi.fn> | undefined;

    scope.run(() => {
      const { virtualizer } = useBlinkVirtualScroll({
        samples: ref([{ defectId: 1, reviewImages: [] }]),
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

  it("uses global offsets and totals for a pre-filtered paged review window", () => {
    const scope = effectScope();

    scope.run(() => {
      const { samplesForVirtualRow, virtualizer } = useBlinkVirtualScroll({
        samples: ref([
          { defectId: 1_001, reviewImages: [1] },
          { defectId: 1_002, reviewImages: [1] },
        ]),
        mode: ref("review"),
        patchPerRow: ref(2),
        reviewPerRow: ref(2),
        totalSamples: ref(300_000),
        sampleOffset: ref(1_000),
        reviewSamplesArePreFiltered: true,
      });

      expect(samplesForVirtualRow(499)).toEqual([]);
      expect(samplesForVirtualRow(500).map((sample) => sample.defectId)).toEqual([1_001, 1_002]);
      expect(virtualizer.value.getTotalSize()).toBe(150_000 * 156);
    });

    scope.stop();
  });
});
