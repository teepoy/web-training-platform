import type { Meta, StoryObj } from "@storybook/vue3";
import ManualDatasetImporter from "./ManualDatasetImporter.vue";
import { mockImportProps } from "../../../.storybook/mocks/pluginProps";

const meta = {
  component: ManualDatasetImporter,
  title: "Plugins/Import/Manual Dataset Import",
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
} satisfies Meta<typeof ManualDatasetImporter>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: mockImportProps(),
};
