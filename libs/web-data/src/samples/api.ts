import { req, uploadFile } from "../client/apiClient";

export interface Sample {
  id: string;
  dataset_id: string;
  image_uris: string[];
  metadata: Record<string, unknown>;
  ls_task_id?: number | null;
}

export interface LatestAnnotation {
  id: string;
  label: string;
  created_by: string;
  created_at: string;
}

export interface SampleWithLabels {
  id: string;
  dataset_id: string;
  image_uris: string[];
  metadata: Record<string, unknown>;
  ls_task_id?: number | null;
  latest_annotation: LatestAnnotation | null;
}

export interface Annotation {
  id: string;
  sample_id: string;
  label: string;
  created_by: string;
  created_at: string;
}

export interface BulkCreateSampleItem {
  image_uris: string[];
  metadata: Record<string, unknown>;
  label?: string | null;
}

export interface BulkCreateSampleResponse {
  dataset_id: string;
  imported: number;
  failed: number;
  sample_ids: string[];
  ls_task_ids: number[];
  errors: string[];
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
}

export interface FetchSampleSliceOptions {
  offset?: number;
  limit?: number;
  label?: string | null;
  orderBy?: string;
  sampleIds?: string[] | null;
}

export interface UploadResponse {
  uri: string;
  sample_id: string;
  index: number;
}

export interface SimilarityResponse {
  sample_id: string;
  neighbors: Array<{ sample_id: string; score: number }>;
}

export function listSamplesWithLabels(
  datasetId: string,
  offset = 0,
  limit = 50,
  label?: string,
  orderBy = "id",
): Promise<PaginatedResponse<SampleWithLabels>> {
  const params = new URLSearchParams();
  params.set("offset", String(offset));
  params.set("limit", String(limit));
  if (label != null) params.set("label", label);
  params.set("order_by", orderBy);
  return req<PaginatedResponse<SampleWithLabels>>(
    `/datasets/${datasetId}/samples-with-labels?${params.toString()}`,
  );
}

export function listSamples(
  datasetId: string,
  offset?: number,
  limit?: number,
): Promise<PaginatedResponse<Sample>> {
  const params = new URLSearchParams();
  if (offset !== undefined) params.set("offset", String(offset));
  if (limit !== undefined) params.set("limit", String(limit));
  const qs = params.toString() ? `?${params.toString()}` : "";
  return req<PaginatedResponse<Sample>>(
    `/datasets/${datasetId}/samples${qs}`,
  );
}

export function getSample(sampleId: string): Promise<Sample> {
  return req<Sample>(`/samples/${sampleId}`);
}

export function createSample(
  datasetId: string,
  body: { image_uris: string[]; metadata?: Record<string, unknown> },
): Promise<Sample> {
  return req<Sample>(`/datasets/${datasetId}/samples`, {
    method: "POST",
    body: JSON.stringify({
      image_uris: body.image_uris,
      metadata: body.metadata ?? {},
    }),
  });
}

export function importSamples(
  datasetId: string,
  items: BulkCreateSampleItem[],
): Promise<BulkCreateSampleResponse> {
  return req<BulkCreateSampleResponse>(
    `/datasets/${datasetId}/samples/import`,
    {
      method: "POST",
      body: JSON.stringify({ items }),
    },
    120_000,
  );
}

export function fetchSampleSlice(
  datasetId: string,
  options: FetchSampleSliceOptions = {},
): Promise<PaginatedResponse<SampleWithLabels>> {
  const params: Record<string, unknown> = { query_type: "sample-slice", params: {} };
  if (options.offset !== undefined) (params.params as Record<string, unknown>).offset = options.offset;
  if (options.limit !== undefined) (params.params as Record<string, unknown>).limit = options.limit;
  if (options.label !== undefined && options.label !== null)
    (params.params as Record<string, unknown>).label = options.label;
  if (options.orderBy !== undefined) (params.params as Record<string, unknown>).order_by = options.orderBy;
  if (options.sampleIds !== undefined && options.sampleIds !== null) {
    (params.params as Record<string, unknown>).sample_ids = options.sampleIds;
  }

  return req<PaginatedResponse<SampleWithLabels>>(
    `/datasets/${datasetId}/query`,
    {
      method: "POST",
      body: JSON.stringify(params),
    },
  );
}

export function listAnnotationsForSample(sampleId: string): Promise<Annotation[]> {
  return req<Annotation[]>(`/samples/${sampleId}/annotations`);
}

export function createAnnotation(body: {
  sample_id: string;
  label: string;
  created_by?: string;
}): Promise<Annotation> {
  return req<Annotation>("/annotations", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateAnnotation(annotationId: string, payload: { label: string }): Promise<Annotation> {
  return req<Annotation>(`/annotations/${annotationId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteAnnotation(annotationId: string): Promise<void> {
  return req<void>(`/annotations/${annotationId}`, { method: "DELETE" });
}

export function uploadSampleImage(sampleId: string, file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  return uploadFile<UploadResponse>(`/samples/${sampleId}/upload`, form);
}

export function getSimilarity(
  datasetId: string,
  sampleId: string,
  k?: number,
): Promise<SimilarityResponse> {
  const qs = k !== undefined ? `?k=${k}` : "";
  return req<SimilarityResponse>(
    `/datasets/${datasetId}/similarity/${sampleId}${qs}`,
  );
}
