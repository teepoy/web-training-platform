import type { Meta, StoryObj } from "@storybook/vue3";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import TrainingChart from "./TrainingChart.vue";

echarts.use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

const meta = {
  title: "web-ui/components/TrainingChart",
  component: TrainingChart,
} satisfies Meta<typeof TrainingChart>;

export default meta;
type Story = StoryObj<typeof meta>;

export const LineChartStory: Story = {
  args: {
    events: [
      { job_id: "j1", ts: "2025-01-01T00:00:00Z", level: "INFO", message: "epoch 1", payload: { epoch: 1, loss: 0.85 } },
      { job_id: "j1", ts: "2025-01-01T00:01:00Z", level: "INFO", message: "epoch 2", payload: { epoch: 2, loss: 0.62 } },
      { job_id: "j1", ts: "2025-01-01T00:02:00Z", level: "INFO", message: "epoch 3", payload: { epoch: 3, loss: 0.41 } },
    ],
  },
};

export const AggregateStats: Story = {
  args: {
    events: [],
    metricsArtifact: { accuracy: "0.94", f1_score: "0.92", labels: { cat: 120, dog: 115 } },
  },
};

export const Empty: Story = {
  args: {
    events: [],
    metricsArtifact: null,
  },
};
