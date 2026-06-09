import type { Meta, StoryObj } from "@storybook/vue3";
import UpstreamPreviewLauncher from "./UpstreamPreviewLauncher.vue";

const meta = {
  title: "Shared/UpstreamPreviewLauncher",
  component: UpstreamPreviewLauncher,
  args: {
    onComplete: (_result: { sessionId: string }) => {},
    onCancel: () => {},
  },
} satisfies Meta<typeof UpstreamPreviewLauncher>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
