import type { Meta, StoryObj } from "@storybook/vue3";
import ResourcePageShell from "./ResourcePageShell.vue";

const meta = {
  title: "Shared/ResourcePageShell",
  component: ResourcePageShell,
  render: (args) => ({
    components: { ResourcePageShell },
    setup: () => ({ args }),
    template:
      "<ResourcePageShell v-bind='args'><div style='padding: 12px'>Dataset table area</div></ResourcePageShell>",
  }),
  args: {
    isLoading: false,
    hasOrg: true,
    error: null,
  },
} satisfies Meta<typeof ResourcePageShell>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Ready: Story = {};

export const Loading: Story = {
  args: { isLoading: true },
};

export const ErrorState: Story = {
  args: { error: new Error("Failed to load") },
};
