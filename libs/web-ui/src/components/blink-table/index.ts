export { default as BlinkImageCell } from "./BlinkImageCell.vue";
export { default as BlinkTable } from "./BlinkTable.vue";

import { defineAsyncComponent } from "vue";
import { defineDashboardWidget } from "@platform/widget-sdk";

export const blinkTablePlugin = defineDashboardWidget({
  key: "blink-table",
  component: defineAsyncComponent(() => import("./BlinkTableWidget.vue")),
  contract: {
    displayName: "Blink Table",
    description:
      "A/B blink comparison table for multi-image samples. Shows a crossfading blink column (image 1 ↔ image 2) plus static image columns for all images in each sample.",
    acceptsProps: ["data", "config", "size"],
    capabilities: { reads: [], emits: [] },
    selfTests: [{
      name: "renders BlinkTable from inline data",
      objective: "Verify the widget renders BlinkTable when provided with rows and columns.",
      steps: ["Provide data.inline.rows with at least one BlinkRow.", "Provide data.inline.columns with at least one BlinkColumnDef."],
      expected: ["BlinkTable component is rendered with the provided rows and columns."],
    }],
  },
});
