import type { Meta, StoryObj } from "@storybook/vue3";
import type { DataTableColumns } from "naive-ui";
import RemoteListTableShell from "./RemoteListTableShell.vue";

interface Row {
  name: string;
  status: string;
}

const columns: DataTableColumns<Row> = [
  { title: "Name", key: "name" },
  { title: "Status", key: "status" },
];

const meta: Meta<typeof RemoteListTableShell> = {
  title: "Resources/RemoteListTableShell",
  component: RemoteListTableShell,
  parameters: { layout: "padded" },
};

export default meta;
type Story = StoryObj<typeof RemoteListTableShell>;

export const NoFilterResults: Story = {
  render: () => ({
    components: { RemoteListTableShell },
    setup: () => ({ columns }),
    template: `
      <RemoteListTableShell
        :columns="columns"
        :data="[]"
        :loading="false"
        :active-filter-count="2"
        empty-description="No collections yet"
        no-results-description="No collections match these filters"
        bordered
      />
    `,
  }),
};

export const LoadFailure: Story = {
  render: () => ({
    components: { RemoteListTableShell },
    setup: () => ({ columns }),
    template: `
      <RemoteListTableShell
        :columns="columns"
        :data="[]"
        :loading="false"
        error="Collections could not be loaded. Try again."
        empty-description="No collections yet"
      />
    `,
  }),
};
