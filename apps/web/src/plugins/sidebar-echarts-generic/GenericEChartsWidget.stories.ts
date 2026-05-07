import type { Meta, StoryObj } from "@storybook/vue3";
import GenericEChartsWidget from "./GenericEChartsWidget.vue";
import { providePluginContext } from "../../../.storybook/mocks/pluginContext";

const meta = {
  component: GenericEChartsWidget,
  title: "Plugins/Sidebar/Generic ECharts",
  decorators: [providePluginContext()],
} satisfies Meta<typeof GenericEChartsWidget>;

export default meta;
type Story = StoryObj<typeof meta>;

export const BarChart: Story = {
  args: {
    data: {
      inline: {
        xAxis: { type: "category", data: ["Mon", "Tue", "Wed", "Thu", "Fri"] },
        yAxis: { type: "value" },
        series: [{ type: "bar", data: [120, 200, 150, 80, 70] }],
      },
    },
  },
};

export const LineChart: Story = {
  args: {
    data: {
      inline: {
        xAxis: { type: "category", data: ["Jan", "Feb", "Mar", "Apr", "May", "Jun"] },
        yAxis: { type: "value" },
        series: [{ type: "line", data: [820, 932, 901, 934, 1290, 1330], smooth: true }],
      },
    },
  },
};

export const PieChart: Story = {
  args: {
    data: {
      inline: {
        series: [
          {
            type: "pie",
            radius: ["40%", "70%"],
            data: [
              { value: 1048, name: "Search" },
              { value: 735, name: "Direct" },
              { value: 580, name: "Email" },
              { value: 484, name: "Union" },
              { value: 300, name: "Video" },
            ],
          },
        ],
      },
    },
  },
};

export const Compact: Story = {
  args: {
    ...BarChart.args,
    size: "compact",
  },
};

export const Large: Story = {
  args: {
    data: {
      inline: {
        xAxis: { type: "category", data: ["A", "B", "C", "D", "E", "F"] },
        yAxis: { type: "value" },
        series: [
          { type: "bar", data: [320, 280, 350, 410, 380, 290] },
        ],
      },
    },
    size: "large",
    config: { height: 320 },
  },
};

export const Empty: Story = {
  args: {
    data: null,
  },
};
