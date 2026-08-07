import { flushPromises } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { defineComponent } from "vue";
import { mountWithProviders } from "@/testing";

import DatasetTrainTab from "./DatasetTrainTab.vue";

const JobsViewStub = defineComponent({
  name: "JobsView",
  props: {
    datasetId: String,
    allowTrain: { type: Boolean, default: true },
    trainDisabledReason: String,
    compatibleViewTypes: Array,
  },
  template: '<div data-testid="jobs-view" />',
});

describe("DatasetTrainTab", () => {
  it("does not block submission on a sample-level readiness request", async () => {
    const { wrapper } = await mountWithProviders(DatasetTrainTab, {
      props: { datasetId: "dataset-1" },
      global: {
        stubs: {
          JobsView: JobsViewStub,
        },
      },
    });

    await flushPromises();

    const jobsView = wrapper.findComponent(JobsViewStub);
    expect(jobsView.exists()).toBe(true);
    expect(jobsView.props("allowTrain")).toBe(true);
    expect(jobsView.props("trainDisabledReason")).toBeUndefined();
  });
});
