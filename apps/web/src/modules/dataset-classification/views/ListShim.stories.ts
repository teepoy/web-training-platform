import type { Meta, StoryObj } from "@storybook/vue3";
import ClassificationDatasetsShim from "./ListShim.vue";
import { imageClassificationSchema } from "./schema";

const CLASSIFICATION_LABELS = ["cat", "dog", "bird", "car", "truck"];

function makeMockClassificationDatasets(count = 8) {
  return Array.from({ length: count }, (_, i) => {
    const sample = imageClassificationSchema.mockSampleFactory(i, CLASSIFICATION_LABELS) as {
      id: string;
      image_uris: string[];
      metadata: { index: number; label: string };
    };

    return {
      id: sample.id,
      name: `Classification Sample ${i + 1}`,
      dataset_type: "image_classification" as const,
      task_spec: { task_type: "classification" as const, label_space: CLASSIFICATION_LABELS },
      created_at: new Date(Date.now() - i * 86400000).toISOString(),
    };
  });
}

const meta = {
  component: ClassificationDatasetsShim,
  title: "Datasets/Shims/ClassificationDatasetsShim",
  parameters: {
    backgrounds: { default: "light" },
  },
} satisfies Meta<typeof ClassificationDatasetsShim>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    datasets: makeMockClassificationDatasets(8),
    currentOrgId: "mock-org",
    isSuperadmin: false,
    importerFlows: [],
    previewLauncherFlows: [],
  },
};

export const Superadmin: Story = {
  args: {
    datasets: makeMockClassificationDatasets(5),
    currentOrgId: "mock-org",
    isSuperadmin: true,
    importerFlows: [],
    previewLauncherFlows: [],
  },
};

export const Empty: Story = {
  args: {
    datasets: [],
    currentOrgId: "mock-org",
    isSuperadmin: false,
    importerFlows: [],
    previewLauncherFlows: [],
  },
};
