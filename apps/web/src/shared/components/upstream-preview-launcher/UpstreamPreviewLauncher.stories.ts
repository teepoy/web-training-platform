import type { Meta, StoryObj } from "@storybook/vue3";
import UpstreamPreviewLauncher from "./UpstreamPreviewLauncher.vue";

const meta = {
  title: "Shared/UpstreamPreviewLauncher",
  component: UpstreamPreviewLauncher,
  args: {
    onComplete: (result: { sessionId: string }) =>
      console.log("Preview completed:", result.sessionId),
    onCancel: () => console.log("Preview cancelled"),
  },
} satisfies Meta<typeof UpstreamPreviewLauncher>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
