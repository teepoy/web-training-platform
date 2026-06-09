import type { Meta, StoryObj } from "@storybook/vue3";
import DatasetRowActions from "./DatasetRowActions.vue";

const meta = {
  title: "Shared/DatasetRowActions",
  component: DatasetRowActions,
  args: {
    row: {
      id: "ds-1",
      name: "ImageNet Mock",
      dataset_type: "image",
      created_at: new Date().toISOString(),
      is_public: false,
      org_id: "org-1",
      org_name: "Acme",
    },
    isSuperadmin: true,
    isOwnOrg: true,
  },
} satisfies Meta<typeof DatasetRowActions>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const ViewerOnly: Story = {
  args: {
    isSuperadmin: false,
  },
};
