import type { Meta, StoryObj } from "@storybook/vue3";
import PluginTypeSelector from "./PluginTypeSelector.vue";

const meta = {
  title: "web-ui/components/PluginTypeSelector",
  component: PluginTypeSelector,
  args: {
    title: "Select Plugin",
    plugins: [
      { id: "import-manual", label: "Manual Import", description: "Upload files", icon: "\ud83d\udce5", component: null },
      { id: "import-hf", label: "Hugging Face", description: "Load dataset from hub", icon: "\ud83e\udd17", component: null },
    ],
  },
} satisfies Meta<typeof PluginTypeSelector>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Empty: Story = {
  args: {
    plugins: [],
  },
};
