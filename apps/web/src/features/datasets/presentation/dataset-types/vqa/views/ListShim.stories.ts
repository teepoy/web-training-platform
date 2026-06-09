import type { Meta, StoryObj } from "@storybook/vue3";
import VqaDatasetsShim from "./ListShim.vue";
import { imageVqaSchema } from "./schema";

const VQA_QUESTIONS = [
  "What is shown in this image?",
  "Describe the main subject.",
  "What color is the dominant object?",
];

function makeMockVqaDatasets(count = 8) {
  return Array.from({ length: count }, (_, i) => {
    const sample = imageVqaSchema.mockSampleFactory(i) as {
      id: string;
      image_uris: string[];
      metadata: { index: number; question: string };
    };

    return {
      id: sample.id,
      name: `VQA Sample ${i + 1}`,
      dataset_type: "image_vqa" as const,
      task_spec: { task_type: "vqa" as const, questions: VQA_QUESTIONS },
      created_at: new Date(Date.now() - i * 86400000).toISOString(),
    };
  });
}

const meta = {
  component: VqaDatasetsShim,
  title: "Datasets/VQA/ListShim",
  parameters: {
    backgrounds: { default: "light" },
  },
} satisfies Meta<typeof VqaDatasetsShim>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    datasets: makeMockVqaDatasets(8),
    currentOrgId: "mock-org",
    isSuperadmin: false,
    importerFlows: [],
    previewLauncherFlows: [],
  },
};

export const Superadmin: Story = {
  args: {
    datasets: makeMockVqaDatasets(5),
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
