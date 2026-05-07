import type { Meta, StoryObj } from "@storybook/vue3";
import ParquetImporter from "./ParquetImporter.vue";
import { mockImportProps } from "../../../.storybook/mocks/pluginProps";

const meta = {
  component: ParquetImporter,
  title: "Plugins/Import/Parquet Import",
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
} satisfies Meta<typeof ParquetImporter>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: mockImportProps(),
};
