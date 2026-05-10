import type { Meta, StoryObj } from "@storybook/vue3";
import { defineComponent } from "vue";
import DatasetToolbar from "./DatasetToolbar.vue";

const MockPlugin = defineComponent({ template: "<div style='padding: 8px'>Mock flow content</div>" });

const meta = {
  title: "web-ui/components/datasets/DatasetToolbar",
  component: DatasetToolbar,
  args: {
    title: "Datasets",
    importerPlugins: [
      {
        id: "import-manual",
        label: "Manual Import",
        description: "Upload data",
        icon: "\ud83d\udce5",
        component: MockPlugin,
      },
    ],
    previewLauncherPlugins: [
      {
        id: "preview-upstream",
        label: "Upstream Preview",
        description: "Preview samples",
        icon: "\ud83d\udd0d",
        component: MockPlugin,
      },
    ],
  },
} satisfies Meta<typeof DatasetToolbar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
