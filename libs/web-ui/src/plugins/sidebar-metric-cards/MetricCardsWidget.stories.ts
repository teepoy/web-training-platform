import type { Meta, StoryObj } from "@storybook/vue3";
import MetricCardsWidget from "./MetricCardsWidget.vue";

const meta = {
  title: "web-ui/widgets/MetricCardsWidget",
  component: MetricCardsWidget,
  args: {
    data: {
      inline: {
        metrics: [
          { label: "Accuracy", value: "94.1%", color: "#63e2b7" },
          { label: "Loss", value: 0.12, color: "#70c0e8" },
          { label: "Samples", value: 1200 },
          { label: "Epoch", value: 5 },
        ],
      },
    },
    config: {
      columns: 2,
    },
  },
} satisfies Meta<typeof MetricCardsWidget>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
