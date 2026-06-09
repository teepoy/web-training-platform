import type { Meta, StoryObj } from "@storybook/vue3";
import PageProvider from "./PageProvider.vue";

const meta = {
  title: "Shared/PageProvider",
  component: PageProvider,
} satisfies Meta<typeof PageProvider>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => ({
    components: { PageProvider },
    template: `
      <PageProvider>
        <div style="padding: 16px; border: 1px dashed #ccc;">
          Child content
        </div>
      </PageProvider>
    `,
  }),
};
