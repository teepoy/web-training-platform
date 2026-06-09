/** Non-proto types — import flow, summary, and API-only shapes not yet migrated to gRPC. */

export type { ScInspectionSummaryItem as InspectionSummaryItem } from "@/generated/orval/models/scInspectionSummaryItem";
import type { ScInspectionSummaryItem } from "@/generated/orval/models/scInspectionSummaryItem";
import { withAuthQueryParams } from "@/shared/api";

export interface InspectionSummaryPage {
  items: ScInspectionSummaryItem[];
  total: number;
}

export type { ScAnnotationItem } from "@/generated/orval/models/scAnnotationItem";
export type { ScBulkAnnotationResponse as ScBulkAnnotationResult } from "@/generated/orval/models/scBulkAnnotationResponse";
export type { ScBulkAnnotationRequest } from "@/generated/orval/models/scBulkAnnotationRequest";
export type { ScImportRequest } from "@/generated/orval/models/scImportRequest";
export type { ScImportResponse } from "@/generated/orval/models/scImportResponse";

export interface ScImportPayload {
  source_inspection_time: string;
  source_wafer_key: number;
  dataset_name: string;
  storage_mode?: string;
  filters?: Record<string, string>;
  label_space?: string[];
}

export interface ScImportProgressEvent {
  status?: string;
  imported_count?: number;
  remaining_count?: number;
  dataset_id?: string;
  error?: string;
}

export interface ScDatasetInfo {
  id: string;
  name: string;
  label_space: string[];
  task_spec: Record<string, unknown>;
}

/** Construct a patch image proxy URL from inference fields (raw, no auth params). */
export function patchImageUrl(
  inspectionTime: string | bigint,
  waferKey: number,
  defectId: string | number,
  imageType: "template" | "defective" | "difference",
): string {
  const it = String(inspectionTime);
  const did = String(defectId);
  return `/api/v1/sc/images/${encodeURIComponent(it)}/${waferKey}/${encodeURIComponent(did)}/${imageType}`;
}

/** Construct a review image proxy URL from inference fields (raw, no auth params). */
export function reviewImageUrl(
  inspectionTime: string | bigint,
  waferKey: number,
  defectId: string | number,
  imageId: number,
): string {
  const it = String(inspectionTime);
  const did = String(defectId);
  return `/api/v1/sc/images/${encodeURIComponent(it)}/${waferKey}/${encodeURIComponent(did)}/review?review_image_id=${imageId}`;
}

// ── Canonical authenticated image URL types & helpers ─────────────────────

/** Patch image roles recognized by the canonical helpers. */
export type ScPatchImageRole = "template" | "defective" | "difference";

/** Pre-built set of authenticated image URLs for a single defect. */
export interface ScBlinkImageUrls {
  template: string;
  defective: string;
  difference: string;
  review: string[];
}

/** Return an auth-wrapped patch image URL for the given role. */
export function scPatchUrl(
  inspectionTime: string | bigint,
  waferKey: number,
  defectId: string | number,
  role: ScPatchImageRole,
): string {
  return withAuthQueryParams(patchImageUrl(inspectionTime, waferKey, defectId, role));
}

/** Return an auth-wrapped review image URL for a single review image. */
export function scReviewUrl(
  inspectionTime: string | bigint,
  waferKey: number,
  defectId: string | number,
  imageId: number,
): string {
  return withAuthQueryParams(reviewImageUrl(inspectionTime, waferKey, defectId, imageId));
}

/**
 * Build a complete {@link ScBlinkImageUrls} map for a defect, with every
 * URL carrying the current auth token.
 */
export function buildScBlinkImageUrls(
  inspectionTime: string | bigint,
  waferKey: number,
  defectId: string | number,
  reviewImages?: Array<{ imageId: number }>,
): ScBlinkImageUrls {
  return {
    template: scPatchUrl(inspectionTime, waferKey, defectId, "template"),
    defective: scPatchUrl(inspectionTime, waferKey, defectId, "defective"),
    difference: scPatchUrl(inspectionTime, waferKey, defectId, "difference"),
    review: (reviewImages ?? []).map((img) =>
      scReviewUrl(inspectionTime, waferKey, defectId, img.imageId),
    ),
  };
}

/**
 * Normalize a polymorphic image role string (e.g. `"patch_template"`,
 * `"review"`) to a canonical {@link ScPatchImageRole} or `null` if
 * it does not map to a patch role.
 */
export function normalizeScImageRole(raw: string): ScPatchImageRole | null {
  const r = raw.toLowerCase();
  if (r.includes("template")) return "template";
  if (r.includes("defective")) return "defective";
  if (r.includes("difference")) return "difference";
  return null;
}
