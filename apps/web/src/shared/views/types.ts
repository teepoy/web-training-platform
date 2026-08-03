/**
 * View type models — mirrors backend `@view`-registered classes.
 *
 * Each view is a TypeScript interface matching the backend Pydantic model.
 * The view type ID string is the canonical link between frontend and backend.
 */

// ── View type IDs ────────────────────────────────────────────────────────────

export type ViewTypeId = "image_input_v1" | "labeled_image_v1";

// ── View row interfaces ──────────────────────────────────────────────────────

export interface ImageInputV1 {
  sample_id: string;
  image_uris: string[];
}

export interface LabeledImageV1 {
  sample_id: string;
  image_uris: string[];
  label: string;
}

/** Union of all view row types. */
export type ViewRow = ImageInputV1 | LabeledImageV1;

/** Map view type ID to its row interface. */
export interface ViewTypeMap {
  image_input_v1: ImageInputV1;
  labeled_image_v1: LabeledImageV1;
}
