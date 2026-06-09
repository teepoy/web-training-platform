import { mount } from "@vue/test-utils";
import { describe, it, expect, vi } from "vitest";
import BlinkVirtualTableWithSelectionAndPreviewResultDisplay from "./BlinkVirtualTableWithSelectionAndPreviewResultDisplay.vue";
import { nextTick, ref } from "vue";
import type { ScSampleItem } from "@/features/sc/generated/proto/sc/v1/sample_pb";

vi.mock("@/features/sc/presentation/composables/useBlinkVirtualScroll", () => ({
  useBlinkVirtualScroll: () => ({
    virtualizer: {
      getVirtualItems: () => [{ key: 0, index: 0, start: 0, size: 100 }],
      getTotalSize: () => 500,
    },
    virtualRowHeightStr: ref('100px'),
    shouldLoadImages: ref(true),
    queueViewportImageLoad: () => {},
    scrollRef: ref(null),
    visibleSamples: ref([{ defectId: 10 }, { defectId: 11 }]),
    reviewColumnIndices: ref([]),
    imageCellHeightPxStr: ref('60px'),
    samplesForVirtualRow: (idx: number) => [{ defectId: 10 }, { defectId: 11 }],
    effectiveSamplesPerRow: ref(3),
  }),
  ROW_PADDING_Y: 2,
  MINI_HEADER_HEIGHT: 20
}));

vi.mock("@/features/sc/presentation/composables/useBlinkRubberBand", () => ({
  useBlinkRubberBand: () => ({
    rubberBandStyle: ref({}),
    onMouseDown: () => {},
  })
}));

describe("BlinkVirtualTableWithSelectionAndPreviewResultDisplay", () => {
  const mockSamples = [
    { defectId: 10, waferKey: 1, inspectionTime: 1234n, reviewImages: [] },
    { defectId: 11, waferKey: 1, inspectionTime: 1234n, reviewImages: [] },
  ] as unknown as ScSampleItem[];

  function createWrapper(propsData = {}) {
    return mount(BlinkVirtualTableWithSelectionAndPreviewResultDisplay, {
      props: {
        samples: mockSamples,
        ...propsData
      }
    });
  }

  it("renders sample blocks", async () => {
    const wrapper = createWrapper();
    await nextTick();

    const blocks = wrapper.findAll('.sbt-sample-block');
    expect(blocks.length).toBe(2);
  });

  it("changes samples per row without rendering a text input", async () => {
    const wrapper = createWrapper({ patchSamplesPerRow: 3 });
    const control = wrapper.get(".sbt-per-row");

    expect(control.find("input").exists()).toBe(false);
    expect(control.get(".sbt-per-row-value").text()).toBe("3");

    await control.get('[aria-label="Increase samples per row"]').trigger("click");
    expect(control.get(".sbt-per-row-value").text()).toBe("4");
  });

  it("prediction badge visible when predictionLabels prop set", async () => {
    const wrapper = createWrapper({
      showPredictionBadges: true,
      predictionLabels: { '10': 'Scratch' },
      predictionConfidences: { '10': 0.95 }
    });

    await nextTick();

    const badges = wrapper.findAll('.sbt-prediction-badge');
    expect(badges.length).toBe(1);
    expect(badges[0].text()).toContain('Scratch');
    expect(badges[0].text()).toContain('(95%)');
  });

  it("annotationDraft badge visible when annotationDrafts prop set", async () => {
    const wrapper = createWrapper({
      showPredictionBadges: true,
      annotationDrafts: { '11': 'DraftLabel' }
    });

    await nextTick();

    const badges = wrapper.findAll('.sbt-prediction-badge');
    expect(badges.length).toBe(1);
    expect(badges[0].text()).toContain('DraftLabel');
  });
});
