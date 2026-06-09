import { defineAsyncComponent } from "vue";
import { registerDatasetSchema } from "@/features/datasets/presentation/pages/schema-registry";

const VQA_QUESTIONS = [
  "What is shown in this image?",
  "Describe the main subject.",
  "What color is the dominant object?",
];

export const imageVqaSchema = {
  datasetType: "image_vqa",
  taskType: "vqa",
  viewTypes: ["image_input_v1", "qa_input_v1"],
  annotationType: "text" as const,
  shimComponent: defineAsyncComponent(() => import("./ListShim.vue")),
  viewComponent: defineAsyncComponent(() => import("./QAInputView.vue")),
  mockSampleFactory: (index: number, _labelSpace?: string[]) => ({
    id: `vqa-sample-${index}`,
    image_uris: [`https://picsum.photos/seed/vqa${index}/400/300`],
    metadata: { index, question: VQA_QUESTIONS[index % VQA_QUESTIONS.length] },
  }),
};

registerDatasetSchema(imageVqaSchema);
