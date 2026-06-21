import { mount } from "@vue/test-utils";
import { afterEach, describe, it, expect, vi } from "vitest";
import BlinkVirtualTableWithSelectionAndPreviewResultDisplay from "./BlinkVirtualTableWithSelectionAndPreviewResultDisplay.vue";
import { nextTick, ref } from "vue";
import type { ScSampleItem } from "@/features/sc/generated/proto/sc/v1/sample_pb";
import { NRadioGroup } from "naive-ui";

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
    visibleSamples: ref([
      { defectId: 10, waferKey: 1, inspectionTime: 1234n, reviewImages: [{ imageId: 1 }] },
      { defectId: 11, waferKey: 1, inspectionTime: 1234n, reviewImages: [{ imageId: 1 }, { imageId: 2 }, { imageId: 3 }] },
    ]),
    reviewColumnIndices: ref([]),
    imageCellHeightPxStr: ref('60px'),
    samplesForVirtualRow: (_idx: number) => [
      { defectId: 10, waferKey: 1, inspectionTime: 1234n, reviewImages: [{ imageId: 1 }] },
      { defectId: 11, waferKey: 1, inspectionTime: 1234n, reviewImages: [{ imageId: 1 }, { imageId: 2 }, { imageId: 3 }] },
    ],
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
  afterEach(() => {
    document.body.innerHTML = "";
  });

  const mockSamples = [
    { defectId: 10, waferKey: 1, inspectionTime: 1234n, reviewImages: [] },
    { defectId: 11, waferKey: 1, inspectionTime: 1234n, reviewImages: [] },
  ] as unknown as ScSampleItem[];

  function createWrapper(propsData = {}) {
    return mount(BlinkVirtualTableWithSelectionAndPreviewResultDisplay, {
      props: {
        samples: mockSamples,
        ...propsData
      },
      attachTo: document.body,
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
    await wrapper.get("button").trigger("click");
    await nextTick();
    const control = document.body.querySelector(".sbt-per-row");
    expect(control).not.toBeNull();

    expect(control!.querySelector("input")).toBeNull();
    expect(control!.querySelector(".sbt-per-row-value")?.textContent).toBe("3");

    const increase = control!.querySelector('[aria-label="Increase samples per row"]');
    expect(increase).not.toBeNull();
    (increase as HTMLButtonElement).click();
    await nextTick();
    expect(control!.querySelector(".sbt-per-row-value")?.textContent).toBe("4");
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

  it("renders review columns and explicitly requests selected sprite images", async () => {
    const wrapper = createWrapper({
      showModeSwitch: true,
      reviewSamples: mockSamples,
    });

    wrapper.findComponent(NRadioGroup).vm.$emit("update:value", "review");
    await nextTick();

    expect(wrapper.text()).toContain("Rev 1");
    expect(wrapper.text()).toContain("Rev 3");
    expect(wrapper.html()).not.toContain("review_count");
    expect(wrapper.html()).toContain("image_types=patchDefective");
    expect(wrapper.html()).toContain("image_types=patchReference");
    expect(wrapper.html()).toContain("image_types=patchDifference");
    expect(wrapper.html()).toContain("image_types=review1");
    expect(wrapper.html()).toContain("image_types=review3");
  });
});
