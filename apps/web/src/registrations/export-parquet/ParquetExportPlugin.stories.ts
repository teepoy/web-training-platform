import type { Meta, StoryObj } from "@storybook/vue3";
import ParquetExportPlugin from "./ParquetExportPlugin.vue";
import { mockExportProps } from "../../../.storybook/mocks/flowProps";

const meta = {
  component: ParquetExportPlugin,
  title: "Plugins/Export/Parquet Export",
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
} satisfies Meta<typeof ParquetExportPlugin>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: mockExportProps(),
};
