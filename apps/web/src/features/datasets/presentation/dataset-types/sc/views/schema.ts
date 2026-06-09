import { defineAsyncComponent } from "vue";
import { registerDatasetSchema } from "@/features/datasets/presentation/pages/schema-registry";

export const imageScSchema = {
  datasetType: "image_sc",
  // NOTE: "semiconductor" will be added to TaskType union in Task 6.
  // Expected temporary type error:
  taskType: "semiconductor" as "semiconductor",
  viewTypes: ["patch_image_v1", "review_image_v1"],
  annotationType: "none" as const,
  shimComponent: defineAsyncComponent(() => import("./ListShim.vue")),
  viewComponent: defineAsyncComponent(() => import("./ScPatchImageView.vue")),
  selfLoading: true,
  mockSampleFactory: (index: number, _labelSpace?: string[]) => ({
    id: `sc-sample-${index}`,
    template_url: `https://picsum.photos/seed/sc-tpl${index}/400/300`,
    defective_url: `https://picsum.photos/seed/sc-def${index}/400/300`,
    difference_url: `https://picsum.photos/seed/sc-diff${index}/400/300`,
    metadata: { index, inspection_time: "2026-05-23T10:00:00.000Z" },
  }),
};

registerDatasetSchema(imageScSchema);
