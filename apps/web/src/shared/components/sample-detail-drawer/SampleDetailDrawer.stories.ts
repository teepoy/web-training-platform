import type { Meta, StoryObj } from "@storybook/vue3";
import SampleDetailDrawer from "./SampleDetailDrawer.vue";

const meta = {
  title: "Shared/SampleDetailDrawer",
  component: SampleDetailDrawer,
  args: {
    show: true,
    sampleId: "sample-mock-001",
    datasetId: "dataset-mock-001",
    labelSpace: ["cat", "dog", "bird"],
  },
} satisfies Meta<typeof SampleDetailDrawer>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
