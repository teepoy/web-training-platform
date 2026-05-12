import { defineAsyncComponent } from "vue";
import { defineSidebarPlugin } from "@platform/plugin-sdk";

export const sampleViewerPlugin = defineSidebarPlugin({
  key: "sample-viewer",
  component: defineAsyncComponent(
    () => import("../../components/sample-viewer/SampleViewerWidget.vue"),
  ),
  contract: {
    displayName: "Sample Viewer",
    description:
      "Shows sample thumbnails or item previews inside the sidebar.",
    acceptsProps: ["data", "config", "size"],
    capabilities: {
      reads: ["classify-dashboard"],
      emits: [],
    },
    selfTests: [
      {
        name: "renders a sample preview",
        objective: "Verify at least one sample can be shown from panel data.",
        steps: ["Render the widget with one valid sample payload."],
        expected: [
          "A preview element is visible and the widget renders without extra agent wiring.",
        ],
      },
    ],
  },
});
