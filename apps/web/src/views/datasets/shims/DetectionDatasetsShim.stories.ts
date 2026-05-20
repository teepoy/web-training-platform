import type { Meta, StoryObj } from "@storybook/vue3";
import DetectionDatasetsShim from "./DetectionDatasetsShim.vue";
import { imageDetectionSchema } from "../schemas/image-detection";

const DETECTION_LABELS = ["car", "person", "bicycle", "truck", "bus"];

function makeMockDetectionDatasets(count = 8) {
  return Array.from({ length: count }, (_, i) => {
    const sample = imageDetectionSchema.mockSampleFactory(i, DETECTION_LABELS) as {
      id: string;
      image_uris: string[];
      metadata: { boxes: { label: string }[] };
    };
    return {
      id: sample.id,
      name: `Detection Sample ${i + 1}`,
      dataset_type: "image_detection" as const,
      task_spec: { task_type: "detection" as const, label_space: DETECTION_LABELS },
      created_at: new Date(Date.now() - i * 86400000).toISOString(),
    };
  });
}

const meta = {
  component: DetectionDatasetsShim,
  title: "Datasets/Shims/DetectionDatasetsShim",
  parameters: {
    backgrounds: { default: "light" },
  },
} satisfies Meta<typeof DetectionDatasetsShim>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    datasets: makeMockDetectionDatasets(8),
    currentOrgId: "mock-org",
    isSuperadmin: false,
    importerPlugins: [],
    previewLauncherPlugins: [],
  },
};

export const Superadmin: Story = {
  args: {
    datasets: makeMockDetectionDatasets(5),
    currentOrgId: "mock-org",
    isSuperadmin: true,
    importerPlugins: [],
    previewLauncherPlugins: [],
  },
};

export const Empty: Story = {
  args: {
    datasets: [],
    currentOrgId: "mock-org",
    isSuperadmin: false,
    importerPlugins: [],
    previewLauncherPlugins: [],
  },
};
