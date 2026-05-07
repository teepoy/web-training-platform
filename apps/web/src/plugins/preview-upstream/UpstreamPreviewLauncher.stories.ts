import type { Meta, StoryObj } from "@storybook/vue3";
import UpstreamPreviewLauncher from "./UpstreamPreviewLauncher.vue";
import { mockPreviewProps } from "../../../.storybook/mocks/pluginProps";

const meta = {
  component: UpstreamPreviewLauncher,
  title: "Plugins/Preview/Upstream Preview",
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
} satisfies Meta<typeof UpstreamPreviewLauncher>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: mockPreviewProps(),
};
