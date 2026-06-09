import type { Meta, StoryObj } from "@storybook/vue3";
import DatasetSparseSummary from "./DatasetSparseSummary.vue";
import type { SparseSummaryResponse } from "@/generated/orval/models";

const mockSparseSummary: SparseSummaryResponse = {
  dataset_id: "mock-dataset-sparse-1",
  name: "ImageNet-1K Mock",
  dataset_type: "image_classification",
  storage_mode: "file_shard_sparse",
  manifest: {
    shard_count: 4,
    total_rows: 1024,
    created_at: "2026-01-15T10:30:00Z",
    schema_columns: [
      { name: "image_uri", type: "string" },
      { name: "label", type: "string" },
      { name: "metadata", type: "json" },
    ],
  },
  shards: [
    { shard_index: 0, row_count: 256, format: "parquet", byte_size: 1048576 },
    { shard_index: 1, row_count: 256, format: "parquet", byte_size: 1048576 },
    { shard_index: 2, row_count: 256, format: "parquet", byte_size: 1048576 },
    { shard_index: 3, row_count: 256, format: "parquet", byte_size: 1048576 },
  ],
  sample_rows: [
    { image_uri: "s3://bucket/shard0/img001.jpg", label: "cat" },
    { image_uri: "s3://bucket/shard0/img002.jpg", label: "dog" },
    { image_uri: "s3://bucket/shard0/img003.jpg", label: "bird" },
  ],
};

const meta = {
  component: DatasetSparseSummary,
  title: "Datasets/Components/DatasetSparseSummary",
  parameters: {
    backgrounds: { default: "light" },
  },
} satisfies Meta<typeof DatasetSparseSummary>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    datasetId: "mock-dataset-sparse-1",
    sparseSummary: mockSparseSummary,
    isLoading: false,
  },
};

export const Loading: Story = {
  args: {
    datasetId: "mock-dataset-sparse-1",
    sparseSummary: null,
    isLoading: true,
  },
};
