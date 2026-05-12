import type { Meta, StoryObj } from "@storybook/vue3";
import ManualImporter from "./ManualImporter.vue";
import { mockImportProps } from "../../../.storybook/mocks/flowProps";

const meta = {
  component: ManualImporter,
  title: "Plugins/Import/Manual Sample Entry",
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
} satisfies Meta<typeof ManualImporter>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: mockImportProps(),
};
