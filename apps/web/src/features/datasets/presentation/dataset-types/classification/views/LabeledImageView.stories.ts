import type { Meta, StoryObj } from "@storybook/vue3";
import LabeledImageView from "./LabeledImageView.vue";
import type { LabeledImageV1Row } from "@/shared/api/types";

const CLASSIFICATION_LABELS = ["cat", "dog", "bird", "car", "truck"];

function makeMockItems(count = 8): LabeledImageV1Row[] {
  return Array.from({ length: count }, (_, i) => ({
    sample_id: `labeled-sample-${i + 1}`,
    image_uris: [`https://picsum.photos/seed/cls${i}/400/300`],
    label: CLASSIFICATION_LABELS[i % CLASSIFICATION_LABELS.length],
  }));
}

const meta = {
  component: LabeledImageView,
  title: "Datasets/Classification/LabeledImageView",
  parameters: {
    backgrounds: { default: "light" },
  },
} satisfies Meta<typeof LabeledImageView>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    datasetId: "mock-dataset-1",
    items: makeMockItems(8),
    total: 8,
  },
};

export const Empty: Story = {
  args: {
    datasetId: "mock-dataset-1",
    items: [],
    total: 0,
  },
};
