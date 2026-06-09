import type { Meta, StoryObj } from "@storybook/vue3";
import SampleBrowser from "./SampleBrowser.vue";
import type { BrowserItem } from "../../types/components";

const sampleItems: BrowserItem[] = Array.from({ length: 8 }, (_, i) => ({
  id: `sample-${String(i).padStart(3, "0")}`,
  imageSrcs: [`https://picsum.photos/seed/sample${i}/160/160`],
  currentLabel: i % 3 === 0 ? "cat" : i % 3 === 1 ? "dog" : null,
  draftLabel: i % 4 === 0 ? "bird" : null,
  predictionLabel: i % 2 === 0 ? "cat" : "dog",
  predictionConfidence: Math.random() * 0.4 + 0.6,
  predictionId: i % 2 === 0 ? `pred-${i}` : null,
  metadata: {
    filename: `img_${i}.jpg`,
    width: 640,
    height: 480,
  },
  sourceKind: "dataset",
  activationLabel: null,
}));

const meta = {
  title: "Shared/SampleBrowser",
  component: SampleBrowser,
  render: (args) => ({
    components: { SampleBrowser },
    setup: () => ({ args }),
    template:
      '<div style="height: 600px"><SampleBrowser v-bind="args" /></div>',
  }),
  args: {
    items: sampleItems,
    totalCount: 8,
    thumbSize: 120,
    layout: "grid" as const,
    isLoading: false,
    showBottomBar: false,
    showLabelRail: false,
    selectionEnabled: false,
    showCheckboxes: false,
  },
} satisfies Meta<typeof SampleBrowser>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const List: Story = {
  args: {
    layout: "list",
  },
};

export const Loading: Story = {
  args: {
    isLoading: true,
  },
};

export const Selectable: Story = {
  args: {
    selectionEnabled: true,
    showCheckboxes: true,
    showBottomBar: true,
  },
};
