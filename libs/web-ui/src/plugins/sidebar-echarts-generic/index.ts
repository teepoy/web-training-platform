import { defineAsyncComponent } from "vue";
import { defineSidebarPlugin } from "@platform/plugin-sdk";

export const echartsGenericPlugin = defineSidebarPlugin({
  key: "echarts-generic",
  component: defineAsyncComponent(
    () => import("../../components/echarts-generic/GenericEChartsWidget.vue"),
  ),
  contract: {
    displayName: "Generic ECharts",
    description:
      "Renders generic ECharts option payloads for static or agent-driven panels.",
    acceptsProps: ["data", "config", "size"],
    capabilities: {
      reads: [],
      emits: [],
    },
    selfTests: [
      {
        name: "renders minimal chart payload",
        objective:
          "Verify the widget accepts a minimal chart option payload.",
        steps: [
          "Render the widget with a minimal ECharts option object in panel data.",
        ],
        expected: [
          "The widget renders a chart container without contract validation failures.",
        ],
      },
    ],
  },
});
