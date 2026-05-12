import { defineAsyncComponent } from "vue";
import { defineSidebarPlugin } from "@platform/plugin-sdk";

export const blinkTablePlugin = defineSidebarPlugin({
  key: "blink-table",
  component: defineAsyncComponent(() => import("../../components/blink-table/BlinkTableWidget.vue")),
  contract: {
    displayName: "Blink Table",
    description:
      "A/B blink comparison table for multi-image samples. Shows a crossfading blink column (image 1 ↔ image 2) plus static image columns for all images in each sample.",
    acceptsProps: ["data", "config", "size"],
    capabilities: {
      reads: [],
      emits: [],
    },
    selfTests: [
      {
        name: "renders BlinkTable from inline data",
        objective:
          "Verify the widget renders BlinkTable when provided with rows and columns.",
        steps: [
          "Provide data.inline.rows with at least one BlinkRow.",
          "Provide data.inline.columns with at least one BlinkColumnDef.",
        ],
        expected: [
          "BlinkTable component is rendered with the provided rows and columns.",
        ],
      },
    ],
  },
});
