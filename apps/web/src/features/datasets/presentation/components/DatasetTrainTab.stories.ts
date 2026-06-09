import type { Meta, StoryObj } from "@storybook/vue3";
import DatasetTrainTab from "./DatasetTrainTab.vue";

const meta = {
  component: DatasetTrainTab,
  title: "Datasets/Components/DatasetTrainTab",
  parameters: {
    backgrounds: { default: "light" },
  },
} satisfies Meta<typeof DatasetTrainTab>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    datasetId: "mock-dataset-1",
  },
};
