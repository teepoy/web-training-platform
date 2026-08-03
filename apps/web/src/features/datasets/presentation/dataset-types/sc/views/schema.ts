import { defineAsyncComponent } from "vue";
import { registerDatasetSchema } from "@/features/datasets/presentation/pages/schema-registry";

export const imageScSchema = {
  datasetType: "image_sc",
  taskType: "sc",
  viewTypes: ["patch_image_v1", "review_image_v1"],
  annotationType: "none" as const,
  shimComponent: defineAsyncComponent(() => import("./ListShim.vue")),
  mockSampleFactory: (index: number, _labelSpace?: string[]) => ({
    id: `sc-sample-${index}`,
    template_url: `https://picsum.photos/seed/sc-tpl${index}/400/300`,
    defective_url: `https://picsum.photos/seed/sc-def${index}/400/300`,
    difference_url: `https://picsum.photos/seed/sc-diff${index}/400/300`,
    metadata: { index, inspection_time: "2026-05-23T10:00:00.000Z" },
  }),
};

registerDatasetSchema(imageScSchema);
