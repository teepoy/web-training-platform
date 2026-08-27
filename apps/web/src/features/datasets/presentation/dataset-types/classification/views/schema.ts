import { defineAsyncComponent } from "vue";
import { registerDatasetSchema } from "@/features/datasets/presentation/pages/schema-registry";

export const imageClassificationSchema = {
  datasetType: "image_classification",
  taskType: "classification",
  viewTypes: ["image_input_v1", "labeled_image_v1"],
  annotationType: "choice" as const,
  shimComponent: defineAsyncComponent(() => import("./ListShim.vue")),
  viewComponent: defineAsyncComponent(() => import("./LabeledImageView.vue")),
};

registerDatasetSchema(imageClassificationSchema);
