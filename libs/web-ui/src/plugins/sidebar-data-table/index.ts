import { defineAsyncComponent } from "vue";
import { defineSidebarPlugin } from "@platform/plugin-sdk";

export const dataTablePlugin = defineSidebarPlugin({
  key: "data-table",
  component: defineAsyncComponent(
    () => import("../../components/data-table/DataTableWidget.vue"),
  ),
  contract: {
    displayName: "Data Table",
    description:
      "Renders columns and rows from static or agent-supplied data, including linked interactive table mode.",
    acceptsProps: ["data", "config", "size"],
    capabilities: {
      reads: ["interaction-state"],
      emits: [
        "select-samples",
        "select-predictions",
        "apply-filter",
        "clear-selection",
      ],
    },
    selfTests: [
      {
        name: "renders a table row",
        objective:
          "Verify the widget handles a minimal columns-and-rows payload.",
        steps: ["Render the widget with one column and one row."],
        expected: [
          "The first row is visible and the widget does not crash on a small dataset.",
        ],
      },
      {
        name: "interactive row selection",
        objective:
          "Verify row click can emit linked intents and follow shared collection selection state.",
        steps: [
          "Render the widget with object columns, row ids, and config.interaction.collection.",
          "Click a row and inspect emitted intent metadata.",
        ],
        expected: [
          "The widget emits select-* intents with metadata.collection.",
          "Rows in shared selection state are highlighted when followSelection is enabled.",
        ],
      },
    ],
  },
});
