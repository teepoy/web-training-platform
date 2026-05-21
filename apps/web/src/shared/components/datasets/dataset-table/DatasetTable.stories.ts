import type { Meta, StoryObj } from "@storybook/vue3";
import { h } from "vue";
import type { DataTableColumns } from "naive-ui";
import DatasetTable from "./DatasetTable.vue";

interface StoryDataset {
  id: string;
  name: string;
  dataset_type: string;
  created_at: string;
}

const rows: StoryDataset[] = [
  { id: "ds-1", name: "ImageNet Mock", dataset_type: "image", created_at: new Date().toISOString() },
  { id: "ds-2", name: "Oxford Flowers", dataset_type: "image", created_at: new Date().toISOString() },
];

const columns: DataTableColumns<StoryDataset> = [
  { title: "Name", key: "name" },
  { title: "Type", key: "dataset_type" },
  {
    title: "Created",
    key: "created_at",
    render: (row) => h("span", new Date(row.created_at).toLocaleString()),
  },
];

const meta = {
  title: "web-ui/components/datasets/DatasetTable",
  component: DatasetTable,
  args: {
    datasets: rows,
    columns,
    onRowClick: () => {},
  },
} satisfies Meta<typeof DatasetTable>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
