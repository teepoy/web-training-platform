import { describe, expect, it } from "vitest";
import { NPopconfirm } from "naive-ui";
import { mountWithProviders } from "@/testing";
import ReclassifyAnnotationSidebar from "./ReclassifyAnnotationSidebar.vue";

describe("ReclassifyAnnotationSidebar", () => {
  it("requires confirmation before clearing every draft", async () => {
    const { wrapper } = await mountWithProviders(ReclassifyAnnotationSidebar, {
      props: {
        selectedCount: 0,
        codeLabels: [],
        annotationDraft: { "sample-1": "Scratch" },
        draftCount: 1,
        selectedDraftCount: 0,
        isSubmitting: false,
      },
    });

    await wrapper.get('[data-testid="clear-drafts-trigger"]').trigger("click");
    expect(wrapper.emitted("clear-drafts")).toBeUndefined();

    wrapper.findComponent(NPopconfirm).vm.$emit("positive-click");
    expect(wrapper.emitted("clear-drafts")).toHaveLength(1);
  });
});
