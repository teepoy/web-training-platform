import type { Meta, StoryObj } from "@storybook/vue3";
import { defineComponent } from "vue";
import FlowModal from "./FlowModal.vue";

const MockPluginComponent = defineComponent({
  template: "<div style='padding: 8px'>Mock plugin content</div>",
});

const meta = {
  title: "web-ui/components/FlowModal",
  component: FlowModal,
  args: {
    show: true,
    kind: "import",
    title: "Import Dataset",
    datasetId: "dataset-001",
    flows: [
      {
        id: "import-manual",
        label: "Manual Import",
        description: "Upload files",
        icon: "\ud83d\udce5",
        component: MockPluginComponent,
      },
    ],
  },
} satisfies Meta<typeof FlowModal>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
