import type { Meta, StoryObj } from "@storybook/vue3";
import PreviewItemDrawer from "./PreviewItemDrawer.vue";
import type { PreviewItem } from "../../types/components";

const sampleItem: PreviewItem = {
  upstream_item_id: "upstream-001",
  image_uris: ["https://picsum.photos/300/200?random=99"],
  metadata: {
    filename: "sample_001.jpg",
    source: "imagenet",
    class_name: "tabby cat",
  },
};

const meta = {
  title: "web-ui/components/PreviewItemDrawer",
  component: PreviewItemDrawer,
  args: {
    show: true,
    item: sampleItem,
  },
} satisfies Meta<typeof PreviewItemDrawer>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const NoMetadata: Story = {
  args: {
    item: {
      ...sampleItem,
      metadata: {},
    },
  },
};

export const NullItem: Story = {
  args: {
    show: true,
    item: null,
  },
};
