import type { Meta, StoryObj } from "@storybook/vue3";
import GenericEChartsWidget from "./GenericEChartsWidget.vue";

const meta = {
  title: "web-ui/widgets/GenericEChartsWidget",
  component: GenericEChartsWidget,
  args: {
    data: {
      inline: {
        tooltip: {},
        xAxis: { type: "category", data: ["A", "B", "C"] },
        yAxis: { type: "value" },
        series: [{ type: "bar", data: [12, 20, 15] }],
      },
    },
    size: "normal",
  },
} satisfies Meta<typeof GenericEChartsWidget>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
