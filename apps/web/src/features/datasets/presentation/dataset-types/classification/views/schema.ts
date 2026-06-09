import { defineAsyncComponent } from "vue";
import { registerDatasetSchema } from "@/features/datasets/presentation/pages/schema-registry";

export const imageClassificationSchema = {
  datasetType: "image_classification",
  taskType: "classification",
  viewTypes: ["image_input_v1", "labeled_image_v1"],
  annotationType: "choice" as const,
  shimComponent: defineAsyncComponent(() => import("./ListShim.vue")),
  viewComponent: defineAsyncComponent(() => import("./LabeledImageView.vue")),
  mockSampleFactory: (index: number, labelSpace?: string[]) => {
    const labels = labelSpace?.length ? labelSpace : ["unknown"];
    return {
      id: `cls-sample-${index}`,
      image_uris: [`https://picsum.photos/seed/cls${index}/400/300`],
      metadata: { index, label: labels[index % labels.length] },
    };
  },
};

registerDatasetSchema(imageClassificationSchema);
