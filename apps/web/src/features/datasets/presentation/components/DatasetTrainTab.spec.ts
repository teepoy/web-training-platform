import { flushPromises } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { defineComponent } from "vue";
import { http, HttpResponse } from "msw";

import { mountWithProviders } from "@/testing";
import { server } from "@/testing/msw/server";

import DatasetTrainTab from "./DatasetTrainTab.vue";

const JobsViewStub = defineComponent({
  name: "JobsView",
  props: {
    datasetId: String,
    allowTrain: Boolean,
    trainDisabledReason: String,
    compatibleViewTypes: Array,
  },
  template: '<div data-testid="jobs-view" />',
});

describe("DatasetTrainTab", () => {
  it("passes dataset status training disable information to the jobs view", async () => {
    server.use(
      http.get("/api/v1/datasets/dataset-1/status", () =>
        HttpResponse.json({
          allow_train: false,
          train_disabled_reason: "insufficient_active_classes",
          minimum_active_class_count: 2,
          active_class_count: 1,
          annotated_samples: 5,
          total_samples: 10,
        }),
      ),
    );

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
    expect(jobsView.props("allowTrain")).toBe(false);
    expect(jobsView.props("trainDisabledReason")).toBe(
      "Training requires at least 2 active classes; currently 1.",
    );
  });
});
