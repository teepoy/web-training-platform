import type { Meta, StoryObj } from "@storybook/vue3";
import SampleBrowser from "./SampleBrowser.vue";
import type { BrowserItem } from "../../types/components";

const browserItems: BrowserItem[] = Array.from({ length: 20 }, (_, i) => ({
  id: `item-${String(i).padStart(3, "0")}`,
  imageSrcs: [`https://picsum.photos/160/160?random=${i}`],
  metadata: { filename: `sample_${i}.jpg`, index: i },
  currentLabel: i % 3 === 0 ? "cat" : i % 3 === 1 ? "dog" : null,
  draftLabel: i % 5 === 0 ? "bird" : null,
  predictionLabel: i % 2 === 0 ? "cat" : "dog",
  predictionConfidence: Math.random() * 0.5 + 0.5,
  predictionId: `pred-${i}`,
  sourceKind: "dataset" as const,
  activationLabel: null,
}));

const meta = {
  title: "web-ui/components/SampleBrowser",
  component: SampleBrowser,
  decorators: [
    () => ({
      template: '<div style="height: 600px"><story /></div>',
    }),
  ],
  args: {
    items: browserItems,
    totalCount: 20,
    thumbSize: 160,
    layout: "grid",
    isLoading: false,
    selectionEnabled: false,
    showCheckboxes: false,
    showBottomBar: false,
    showLabelRail: false,
    activationMode: "open",
  },
  argTypes: {
    "open-item": { action: "open-item" },
    select: { action: "select" },
    "load-more": { action: "load-more" },
  },
} satisfies Meta<typeof SampleBrowser>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Grid: Story = {};

export const List: Story = {
  args: {
    layout: "list",
  },
};

export const WithSelection: Story = {
  args: {
    selectionEnabled: true,
    showCheckboxes: true,
    showBottomBar: true,
  },
};

export const Loading: Story = {
  args: {
    isLoading: true,
  },
};

export const Empty: Story = {
  args: {
    items: [],
    totalCount: 0,
  },
};
