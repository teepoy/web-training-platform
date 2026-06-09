import type { Meta, StoryObj } from "@storybook/vue3";
import BoxDetectionView from "./BoxDetectionView.vue";
import type { BoxDetectionV1Row, BoxV1Row } from "@/shared/api/types";

const DETECTION_LABELS = ["car", "person", "bicycle", "truck", "bus"];

function makeMockBoxes(count: number): BoxV1Row[] {
  return Array.from({ length: count }, (_, i) => ({
    label: DETECTION_LABELS[i % DETECTION_LABELS.length],
    x: 10 + i * 30,
    y: 20 + i * 25,
    width: 80 + i * 10,
    height: 60 + i * 8,
  }));
}

function makeMockItems(count = 8): BoxDetectionV1Row[] {
  return Array.from({ length: count }, (_, i) => ({
    sample_id: `detection-sample-${i + 1}`,
    image_uris: [`https://picsum.photos/seed/det${i}/400/300`],
    boxes: makeMockBoxes((i % 3) + 1),
    width: 400,
    height: 300,
  }));
}

const meta = {
  component: BoxDetectionView,
  title: "Datasets/Detection/BoxDetectionView",
  parameters: {
    backgrounds: { default: "light" },
  },
} satisfies Meta<typeof BoxDetectionView>;

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
