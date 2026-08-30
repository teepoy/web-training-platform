import { z } from "zod";

const timestamp = z
  .string()
  .refine(
    (value) => /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value)),
    "timestamp must be a valid ISO-8601 value with a timezone",
  )
  .transform((value) => new Date(value));

const integer = z.number().int();

export const inspectionKeySchema = z.strictObject({
  wafer_key: integer,
  inspection_time: timestamp,
});

export const defectSchema = z.strictObject({
  defect_id: integer,
  test_id: integer,
  class_number: integer,
  rough_bin: integer,
  wafer_x: integer,
  wafer_y: integer,
  index_x: integer,
  index_y: integer,
  adder: integer,
  cluster: integer,
  images: integer,
  size_x: integer,
  size_y: integer,
  size_d: integer,
  area: integer,
  final_bin: integer,
  manual_bin: integer,
  kill_ratio: z.number(),
});

export const reviewImageSchema = z.strictObject({
  defect_id: integer,
  image_id: integer,
  image_type: z.string(),
  image_filespec: z.string(),
});

export const patchArchiveSchema = z.strictObject({
  archive_id: integer,
  s3_bucket: z.string(),
  s3_key: z.string(),
});

const inspectionFields = {
  wafer_key: integer,
  inspection_time: timestamp,
  lot_id: z.string(),
  wafer_id: z.string(),
  layer_id: z.string(),
  device: z.string(),
  inspect_equip_id: z.string(),
  recipe_key: integer,
  recipe_id: z.string(),
  origin_index_x: integer,
  origin_index_y: integer,
  center_x: integer,
  center_y: integer,
  origin_x: integer,
  origin_y: integer,
  die_size_x: integer,
  die_size_y: integer,
};

export const createInspectionSchema = z.strictObject({
  ...inspectionFields,
  defects: z.array(defectSchema),
  review_images: z.array(reviewImageSchema),
  patch_archives: z.array(patchArchiveSchema),
});

export const appendRecordsSchema = z
  .strictObject({
    ...inspectionKeySchema.shape,
    defects: z.array(defectSchema),
    review_images: z.array(reviewImageSchema),
    patch_archives: z.array(patchArchiveSchema),
  })
  .refine(
    (body) =>
      body.defects.length > 0 || body.review_images.length > 0 || body.patch_archives.length > 0,
    "at least one child record is required",
  );

export const publishInspectionSchema = z.strictObject({
  ...inspectionKeySchema.shape,
  published_at: timestamp,
});

const mutableInspectionFields = {
  lot_id: z.string(),
  wafer_id: z.string(),
  layer_id: z.string(),
  device: z.string(),
  inspect_equip_id: z.string(),
  recipe_key: integer,
  recipe_id: z.string(),
  origin_index_x: integer,
  origin_index_y: integer,
  center_x: integer,
  center_y: integer,
  origin_x: integer,
  origin_y: integer,
  die_size_x: integer,
  die_size_y: integer,
};

export const updateInspectionSchema = z
  .strictObject({
    ...inspectionKeySchema.shape,
    changed_at: timestamp,
    ...Object.fromEntries(
      Object.entries(mutableInspectionFields).map(([name, value]) => [name, value.optional()]),
    ),
  })
  .refine(
    (body) =>
      Object.keys(mutableInspectionFields).some(
        (name) => body[name as keyof typeof body] !== undefined,
      ),
    "at least one mutable field is required",
  );

export const showcaseScenarioSchema = z.strictObject({
  inspection_time: timestamp,
  published_at: timestamp,
  total_defects: integer,
  imaged_defects: integer,
  images_per_defect: integer,
  gallery_defects: integer,
  gallery_imaged_defects: integer,
  defects_per_archive: integer,
  append_batch_size: integer,
});

export type InspectionKey = z.infer<typeof inspectionKeySchema>;
export type DefectInput = z.infer<typeof defectSchema>;
export type ReviewImageInput = z.infer<typeof reviewImageSchema>;
export type PatchArchiveInput = z.infer<typeof patchArchiveSchema>;
export type CreateInspectionInput = z.infer<typeof createInspectionSchema>;
export type AppendRecordsInput = z.infer<typeof appendRecordsSchema>;
export type PublishInspectionInput = z.infer<typeof publishInspectionSchema>;
export type UpdateInspectionInput = z.infer<typeof updateInspectionSchema>;
export type ShowcaseScenarioInput = z.infer<typeof showcaseScenarioSchema>;

export type InspectionResponse = {
  wafer_key: number;
  inspection_time: string;
  lot_id: string;
  wafer_id: string;
  layer_id: string;
  device: string;
  inspect_equip_id: string;
  recipe_key: number;
  recipe_id: string;
  origin_index_x: number;
  origin_index_y: number;
  center_x: number;
  center_y: number;
  origin_x: number;
  origin_y: number;
  die_size_x: number;
  die_size_y: number;
  state: "draft" | "published";
  published_at: string | null;
  last_updated_at: string | null;
  change_token: number | null;
};
