import type { Meta, StoryObj } from "@storybook/vue3";
import { defineComponent } from "vue";
import PluginFlowModal from "./PluginFlowModal.vue";

const MockPluginComponent = defineComponent({
  template: "<div style='padding: 8px'>Mock plugin content</div>",
});

const meta = {
  title: "web-ui/components/PluginFlowModal",
  component: PluginFlowModal,
  args: {
    show: true,
    kind: "import",
    title: "Import Dataset",
    datasetId: "dataset-001",
    plugins: [
      {
        id: "import-manual",
        label: "Manual Import",
        description: "Upload files",
        icon: "\ud83d\udce5",
        component: MockPluginComponent,
      },
    ],
  },
} satisfies Meta<typeof PluginFlowModal>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
