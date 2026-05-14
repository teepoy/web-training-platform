import { req, uploadFile } from "./client";
import type {
  Annotation,
  Sample,
  SampleWithLabels,
  BulkCreateSampleItem,
  BulkCreateSampleResponse,
  PaginatedResponse,
  UploadResponse,
  CreateSampleBody,
} from "./types";

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

export function createSample(
  datasetId: string,
  body: CreateSampleBody,
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

export function getSample(sampleId: string): Promise<Sample> {
  return req<Sample>(`/samples/${sampleId}`);
}

export function uploadSampleImage(
  sampleId: string,
  file: File,
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  return uploadFile<UploadResponse>(`/samples/${sampleId}/upload`, form);
}

export function listAnnotationsForSample(
  sampleId: string,
): Promise<Annotation[]> {
  return req<Annotation[]>(`/samples/${sampleId}/annotations`);
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
