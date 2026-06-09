import { defineAsyncComponent } from "vue";
import { registerDatasetSchema } from "@/features/datasets/presentation/pages/schema-registry";

const DETECTION_LABELS = ["car", "person", "bicycle", "truck", "bus"];

export const imageDetectionSchema = {
  datasetType: "image_detection",
  taskType: "detection",
  viewTypes: ["image_input_v1", "box_detection_v1"],
  annotationType: "boxes" as const,
  shimComponent: defineAsyncComponent(() => import("./ListShim.vue")),
  viewComponent: defineAsyncComponent(() => import("./BoxDetectionView.vue")),
  mockSampleFactory: (index: number, labelSpace?: string[]) => {
    const labels = labelSpace?.length ? labelSpace : DETECTION_LABELS;
    const label = labels[index % labels.length];
    const x = ((index * 13) % 60) / 100;
    const y = ((index * 17) % 60) / 100;
    const boxes = [{ label, x, y, width: 0.25, height: 0.2 }];
    if (index % 5 === 0) {
      const label2 = labels[(index + 2) % labels.length];
      boxes.push({ label: label2, x: x + 0.3, y: y + 0.3, width: 0.2, height: 0.15 });
    }
    return {
      id: `det-sample-${index}`,
      image_uris: [`https://picsum.photos/seed/det${index}/640/480`],
      metadata: { width: 640, height: 480, boxes },
    };
  },
};

registerDatasetSchema(imageDetectionSchema);
