import type { Meta, StoryObj } from "@storybook/vue3";
import SampleViewerWidget from "./SampleViewerWidget.vue";

const meta = {
  title: "Shared/SampleViewerWidget",
  component: SampleViewerWidget,
  args: {
    data: {
      inline: {
        sampleIds: ["s1", "s2"],
        mode: "grid",
        samples: [
          { id: "s1", image_srcs: ["https://picsum.photos/seed/sample1/120/120"], label: "cat" },
          { id: "s2", image_srcs: ["https://picsum.photos/seed/sample2/120/120"], label: "dog" },
        ],
      },
    },
    config: {
      thumbSize: 80,
    },
  },
} satisfies Meta<typeof SampleViewerWidget>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const ListMode: Story = {
  args: {
    data: {
      inline: {
        sampleIds: ["s1", "s2"],
        mode: "list",
        samples: [
          { id: "s1", image_srcs: ["https://picsum.photos/seed/sample1/120/120"], label: "cat" },
          { id: "s2", image_srcs: ["https://picsum.photos/seed/sample2/120/120"], label: "dog" },
        ],
      },
    },
  },
};
