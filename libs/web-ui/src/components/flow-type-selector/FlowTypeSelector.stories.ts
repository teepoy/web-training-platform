import type { Meta, StoryObj } from "@storybook/vue3";
import FlowTypeSelector from "./FlowTypeSelector.vue";

const meta = {
  title: "web-ui/components/FlowTypeSelector",
  component: FlowTypeSelector,
  args: {
    title: "Select Plugin",
    flows: [
      { id: "import-manual", label: "Manual Import", description: "Upload files", icon: "\ud83d\udce5", component: null },
      { id: "import-hf", label: "Hugging Face", description: "Load dataset from hub", icon: "\ud83e\udd17", component: null },
    ],
  },
} satisfies Meta<typeof FlowTypeSelector>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Empty: Story = {
  args: {
    flows: [],
  },
};
