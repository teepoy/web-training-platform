import { beforeAll, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";

// jsdom does not provide ResizeObserver — SampleBrowser uses it in onMounted
beforeAll(() => {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal("ResizeObserver", ResizeObserverStub);
});

import { mockTanstackVirtual } from "@/testing/mocks/tanstack-virtual";
mockTanstackVirtual();

import { mountWithProviders } from "@/testing";
import AnnotationGrid from "./AnnotationGrid.vue";
import type { AnnotationGridItem } from "../../types/components";

const annotationItems: AnnotationGridItem[] = Array.from({ length: 15 }, (_, i) => ({
  id: `ann-${String(i).padStart(3, "0")}`,
  imageSrcs: [`https://picsum.photos/160/160?random=${i + 10}`],
  currentLabel: i % 3 === 0 ? "cat" : i % 3 === 1 ? "dog" : null,
  draftLabel: i % 5 === 0 ? "bird" : null,
  predictionLabel: i % 2 === 0 ? "cat" : "dog",
  predictionConfidence: Math.random() * 0.5 + 0.5,
  predictionId: `pred-${i}`,
  metadata: { filename: `img_${i}.jpg` },
}));

const labelSpace = ["cat", "dog", "bird", "fish", "rabbit"];

describe("AnnotationGrid", () => {
  it("renders grid with label buttons and submit button", async () => {
    const { wrapper } = await mountWithProviders(AnnotationGrid, {
      props: {
        items: annotationItems,
        totalCount: 15,
        labelSpace,
        thumbSize: 160,
        layout: "grid",
      },
    });

    await nextTick();

    expect(wrapper.find(".ag-label-panel").exists()).toBe(true);

    const labelItems = wrapper.findAll(".ag-label-item");
    expect(labelItems).toHaveLength(labelSpace.length);
    labelSpace.forEach((label, idx) => {
      expect(labelItems[idx]!.text()).toContain(label);
    });

    const submitBtn = wrapper.find(".ag-submit-btn");
    expect(submitBtn.exists()).toBe(true);
    expect(submitBtn.text()).toContain("Submit 3");
  });

  it("hides label panel and submit when readOnly is true", async () => {
    const { wrapper } = await mountWithProviders(AnnotationGrid, {
      props: {
        items: annotationItems,
        totalCount: 15,
        labelSpace,
        readOnly: true,
      },
    });

    await nextTick();

    expect(wrapper.find(".ag-label-panel").exists()).toBe(false);
    expect(wrapper.find(".ag-submit-btn").exists()).toBe(false);
  });

  it("disables submit button when submitting is true", async () => {
    const { wrapper } = await mountWithProviders(AnnotationGrid, {
      props: {
        items: annotationItems,
        totalCount: 15,
        labelSpace,
        submitting: true,
      },
    });

    await nextTick();

    const submitBtn = wrapper.find(".ag-submit-btn");
    expect(submitBtn.exists()).toBe(true);
    expect(submitBtn.text()).toContain("Submitting...");
    expect(submitBtn.element.hasAttribute("disabled")).toBe(true);
  });

  it("shows loading indicator when isLoading is true", async () => {
    const { wrapper } = await mountWithProviders(AnnotationGrid, {
      props: {
        items: annotationItems,
        totalCount: 15,
        labelSpace,
        isLoading: true,
      },
    });

    await nextTick();

    const loadingEl = wrapper.find(".sb-loading");
    expect(loadingEl.exists()).toBe(true);
    expect(loadingEl.text()).toContain("Loading more...");
  });

  it('emits "apply-label" when a label button is clicked', async () => {
    const { wrapper } = await mountWithProviders(AnnotationGrid, {
      props: {
        items: annotationItems,
        totalCount: 15,
        labelSpace,
      },
    });

    await nextTick();

    (wrapper.vm as unknown as { selectedIds: Set<string> }).selectedIds = new Set(["ann-000"]);
    await nextTick();

    const firstLabel = wrapper.find(".ag-label-item");
    expect(firstLabel.exists()).toBe(true);
    await firstLabel.trigger("click");

    const emitted = wrapper.emitted("apply-label");
    expect(emitted).toBeDefined();
    expect(emitted).toHaveLength(1);
    expect(emitted![0]).toEqual([{ ids: ["ann-000"], label: "cat" }]);
  });
});
