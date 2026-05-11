import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";

vi.mock("echarts/core", () => ({
  use: vi.fn(),
}));

vi.mock("vue-echarts", () => ({
  default: defineComponent({
    name: "VChart",
    props: ["option", "theme", "autoresize"],
    setup() {
      return () => h("div", { class: "mock-vchart" });
    },
  }),
}));

import TrainingChart from "./TrainingChart.vue";

describe("TrainingChart", () => {
  it("renders chart container when epoch/loss events are provided", () => {
    const events = [
      { job_id: "j1", ts: "2025-01-01T00:00:00Z", level: "INFO", message: "epoch 1", payload: { epoch: 1, loss: 0.85 } },
      { job_id: "j1", ts: "2025-01-01T00:01:00Z", level: "INFO", message: "epoch 2", payload: { epoch: 2, loss: 0.62 } },
    ];
    const wrapper = mount(TrainingChart, {
      props: { events, metricsArtifact: null },
    });
    expect(wrapper.find(".training-chart").exists()).toBe(true);
    expect(wrapper.html()).not.toContain("No training metrics available yet");
  });

  it("renders stats grid when metricsArtifact is provided", () => {
    const wrapper = mount(TrainingChart, {
      props: {
        events: [],
        metricsArtifact: { accuracy: "0.94", f1_score: "0.92" },
      },
    });
    const html = wrapper.html();
    expect(html).toContain("accuracy");
    expect(html).toContain("f1 score");
  });

  it("renders empty state when no data is provided", () => {
    const wrapper = mount(TrainingChart, {
      props: {
        events: [],
        metricsArtifact: null,
      },
    });
    expect(wrapper.html()).toContain("No training metrics available yet");
  });
});
