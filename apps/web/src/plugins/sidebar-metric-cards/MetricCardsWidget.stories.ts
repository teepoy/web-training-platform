import type { Meta, StoryObj } from "@storybook/vue3";
import { MetricCardsWidget } from "@platform/web-ui";
import { providePluginContext } from "../../../.storybook/mocks/pluginContext";

const meta = {
  component: MetricCardsWidget,
  title: "Plugins/Sidebar/Metric Cards",
  decorators: [providePluginContext()],
} satisfies Meta<typeof MetricCardsWidget>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    data: {
      inline: {
        metrics: [
          { label: "Accuracy", value: "94.2%", color: "#63e2b7" },
          { label: "Loss", value: "0.31", color: "#f0a020" },
          { label: "Epoch", value: "12", color: "#70c0e8" },
          { label: "Samples", value: "1,024" },
        ],
      },
    },
  },
};

export const Compact: Story = {
  args: {
    ...Default.args,
    size: "compact",
    config: { columns: 2 },
  },
};

export const Large: Story = {
  args: {
    ...Default.args,
    size: "large",
    config: { columns: 4 },
  },
};

export const Empty: Story = {
  args: {
    data: null,
  },
};

export const SingleMetric: Story = {
  args: {
    data: {
      inline: {
        metrics: [{ label: "Score", value: "0.97", color: "#63e2b7" }],
      },
    },
    config: { columns: 1 },
  },
};

export const ManyMetrics: Story = {
  args: {
    data: {
      inline: {
        metrics: [
          { label: "Precision", value: "92%", color: "#63e2b7" },
          { label: "Recall", value: "88%", color: "#70c0e8" },
          { label: "F1", value: "90%", color: "#f0a020" },
          { label: "AUC", value: "0.95", color: "#e040fb" },
          { label: "Samples", value: "2,048" },
          { label: "Epoch", value: "24" },
        ],
      },
    },
    config: { columns: 3 },
  },
};
