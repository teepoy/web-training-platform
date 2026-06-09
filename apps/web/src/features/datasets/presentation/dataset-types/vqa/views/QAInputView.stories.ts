import type { Meta, StoryObj } from "@storybook/vue3";
import QAInputView from "./QAInputView.vue";
import type { QAInputV1Row } from "@/shared/api/types";

const VQA_QUESTIONS = [
  "What is shown in this image?",
  "Describe the main subject.",
  "What color is the dominant object?",
  "How many objects are in the scene?",
  "What is the person doing?",
];

function makeMockItems(count = 8): QAInputV1Row[] {
  return Array.from({ length: count }, (_, i) => ({
    sample_id: `qa-sample-${i + 1}`,
    image_uris: [`https://picsum.photos/seed/vqa${i}/400/300`],
    question: VQA_QUESTIONS[i % VQA_QUESTIONS.length],
  }));
}

const meta = {
  component: QAInputView,
  title: "Datasets/VQA/QAInputView",
  parameters: {
    backgrounds: { default: "light" },
  },
} satisfies Meta<typeof QAInputView>;

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
