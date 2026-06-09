import type { Meta, StoryObj } from "@storybook/vue3";
import DatasetPageShell from "./DatasetPageShell.vue";

const meta = {
  title: "Shared/DatasetPageShell",
  component: DatasetPageShell,
  render: (args) => ({
    components: { DatasetPageShell },
    setup: () => ({ args }),
    template: "<DatasetPageShell v-bind='args'><div style='padding: 12px'>Dataset table area</div></DatasetPageShell>",
  }),
  args: {
    isLoading: false,
    hasOrg: true,
    error: null,
  },
} satisfies Meta<typeof DatasetPageShell>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Ready: Story = {};

export const Loading: Story = {
  args: { isLoading: true },
};

export const ErrorState: Story = {
  args: { error: new Error("Failed to load") },
};
