import { describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { NMessageProvider } from "naive-ui";
import { mountWithProviders } from "@/testing";
import ModelImporter from "./ModelImporter.vue";

describe("ModelImporter", () => {
  it("derives training job and format from the portable package", async () => {
    const harness = defineComponent({
      setup: () => () =>
        h(NMessageProvider, null, {
          default: () =>
            h(ModelImporter, {
              datasetId: "",
              onComplete: vi.fn(),
              onCancel: vi.fn(),
            }),
        }),
    });
    const { wrapper } = await mountWithProviders(harness);

    expect(wrapper.text()).toContain("Model file");
    expect(wrapper.text()).toContain("Name");
    expect(wrapper.text()).not.toContain("Training job ID");
    expect(wrapper.text()).not.toContain("Format");
  });
});
