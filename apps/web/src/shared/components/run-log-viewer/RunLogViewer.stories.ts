import type { Meta, StoryObj } from "@storybook/vue3";
import RunLogViewer from "./RunLogViewer.vue";

const meta = {
  title: "Shared/RunLogViewer",
  component: RunLogViewer,
  args: {
    runId: "run-mock-001",
  },
} satisfies Meta<typeof RunLogViewer>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
