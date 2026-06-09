import type { Meta, StoryObj } from "@storybook/vue3";
import DatasetPredictTab from "./DatasetPredictTab.vue";

const meta = {
  component: DatasetPredictTab,
  title: "Datasets/Components/DatasetPredictTab",
  parameters: {
    backgrounds: { default: "light" },
  },
} satisfies Meta<typeof DatasetPredictTab>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    datasetId: "mock-dataset-1",
  },
};
