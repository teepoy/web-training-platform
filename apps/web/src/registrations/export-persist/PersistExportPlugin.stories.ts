import type { Meta, StoryObj } from "@storybook/vue3";
import PersistExportPlugin from "./PersistExportPlugin.vue";
import { mockExportProps } from "../../../.storybook/mocks/flowProps";

const meta = {
  component: PersistExportPlugin,
  title: "Plugins/Export/Persist Export",
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
} satisfies Meta<typeof PersistExportPlugin>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: mockExportProps(),
};
