import { defineAsyncComponent } from "vue";
import { registerDatasetSchema } from "../schema-registry";

export const imageClassificationSchema = {
  datasetType: "image_classification",
  taskType: "classification",
  annotationType: "choice" as const,
  shimComponent: defineAsyncComponent(() => import("../shims/ClassificationDatasetsShim.vue")),
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
