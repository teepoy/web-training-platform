import { describe, it, expect } from "vitest";

import { mockEcharts } from "@/testing/mocks/echarts";
mockEcharts();

import { mountWithProviders } from "@/testing";
import TrainingChart from "./TrainingChart.vue";

describe("TrainingChart", () => {
  it("renders chart container when epoch/loss events are provided", async () => {
    const events = [
      {
        job_id: "j1",
        ts: "2025-01-01T00:00:00Z",
        level: "epoch",
        message: "epoch 1",
        payload: { epoch: 1, total_epochs: 2, loss: 0.85, accuracy: 0.6 },
      },
      {
        job_id: "j1",
        ts: "2025-01-01T00:01:00Z",
        level: "epoch",
        message: "epoch 2",
        payload: { epoch: 2, total_epochs: 2, loss: 0.62, accuracy: 0.8 },
      },
    ];
    const { wrapper } = await mountWithProviders(TrainingChart, {
      props: { events, metricsArtifact: null },
    });
    expect(wrapper.find(".training-chart").exists()).toBe(true);
    expect(wrapper.get('[data-testid="training-epoch-progress"]').text()).toContain("Epoch 2 / 2");
    expect(wrapper.get('[data-testid="training-epoch-progress"]').text()).toContain(
      "accuracy 80.0%",
    );
    expect(wrapper.html()).not.toContain("No training metrics available yet");
  });

  it("renders stats grid when metricsArtifact is provided", async () => {
    const { wrapper } = await mountWithProviders(TrainingChart, {
      props: {
        events: [],
        metricsArtifact: { accuracy: "0.94", f1_score: "0.92" },
      },
    });
    const html = wrapper.html();
    expect(html).toContain("accuracy");
    expect(html).toContain("f1 score");
  });

  it("renders empty state when no data is provided", async () => {
    const { wrapper } = await mountWithProviders(TrainingChart, {
      props: {
        events: [],
        metricsArtifact: null,
      },
    });
    expect(wrapper.html()).toContain("No training metrics available yet");
  });
});
