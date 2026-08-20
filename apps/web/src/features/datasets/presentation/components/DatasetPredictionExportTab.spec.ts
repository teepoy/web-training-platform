import { h } from "vue";
import { NMessageProvider } from "naive-ui";
import { describe, expect, it } from "vitest";
import { mountWithProviders } from "@/testing";
import DatasetPredictionExportTab from "./DatasetPredictionExportTab.vue";

describe("DatasetPredictionExportTab", () => {
  it("renders the exporter inline with a plain-language Final Class explanation", async () => {
    const { wrapper } = await mountWithProviders(NMessageProvider, {
      slots: {
        default: () => h(DatasetPredictionExportTab, { datasetId: "dataset-1" }),
      },
    });
    expect(wrapper.text()).toContain("Export current results");
    expect(wrapper.text()).toContain(
      "Uses the annotation when it is classified; otherwise it uses the latest prediction.",
    );
    expect(wrapper.text()).not.toContain("&&");
    expect(wrapper.findComponent({ name: "AsyncComponentWrapper" }).exists()).toBe(true);
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false);

    wrapper.unmount();
  });
});
