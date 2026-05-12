import type { Meta, StoryObj } from "@storybook/vue3";
import PreviewExportPlugin from "./PreviewExportPlugin.vue";
import { mockExportProps } from "../../../.storybook/mocks/flowProps";

const meta = {
  component: PreviewExportPlugin,
  title: "Plugins/Export/Preview Export",
  parameters: {
    backgrounds: { default: "dark" },
  },
  decorators: [
    (story) => ({
      components: { story },
      template:
        '<div style="background: #1a1a2e; min-height: 100vh; padding: 24px; color: #fff;"><story /></div>',
    }),
  ],
} satisfies Meta<typeof PreviewExportPlugin>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: mockExportProps(),
};
