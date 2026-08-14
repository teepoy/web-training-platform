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
      props: {
        datasetId: "dataset-1",
        dataset: {
          id: "dataset-1",
          name: "Dataset",
          dataset_type: "image_classification",
          task_spec: {
            task_type: "classification",
            label_space: ["cat", "dog"],
            metadata_schema: {},
          },
          view_types: ["image_input_v1"],
          org_name: "",
          created_by: "user-1",
          creator_name: "User",
          is_public: false,
          created_at: "2026-08-14T00:00:00Z",
          embed_config: {},
          storage_mode: "db_full",
          dataset_meta: {},
        },
      },
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
