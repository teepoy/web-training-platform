/**
 * View type models — mirrors backend `@view`-registered classes.
 *
 * Each view is a TypeScript interface matching the backend Pydantic model.
 * The view type ID string is the canonical link between frontend and backend.
 */

// ── View type IDs ────────────────────────────────────────────────────────────

export type ViewTypeId =
  | "image_input_v1"
  | "labeled_image_v1"
  | "qa_input_v1"
  | "box_detection_v1";

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

export interface QAInputV1 {
  sample_id: string;
  image_uris: string[];
  question: string;
}

export interface BoxV1 {
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface BoxDetectionV1 {
  sample_id: string;
  image_uris: string[];
  boxes: BoxV1[];
  width?: number;
  height?: number;
}

/** Union of all view row types. */
export type ViewRow = ImageInputV1 | LabeledImageV1 | QAInputV1 | BoxDetectionV1;

/** Map view type ID to its row interface. */
export interface ViewTypeMap {
  image_input_v1: ImageInputV1;
  labeled_image_v1: LabeledImageV1;
  qa_input_v1: QAInputV1;
  box_detection_v1: BoxDetectionV1;
}
