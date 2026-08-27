import { defineAsyncComponent } from "vue";
import { registerDatasetSchema } from "@/features/datasets/presentation/pages/schema-registry";

export const imageScSchema = {
  datasetType: "image_sc",
  taskType: "sc",
  viewTypes: ["patch_image_v1", "review_image_v1"],
  annotationType: "none" as const,
  shimComponent: defineAsyncComponent(() => import("./ListShim.vue")),
};

registerDatasetSchema(imageScSchema);
