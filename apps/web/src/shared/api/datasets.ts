import { req } from "./client";
import { getApiBase } from "./client";
import type {
  Dataset,
  DatasetAnnotationStats,
  SparseSummaryResponse,
  BulkAnnotationRequest,
  BulkAnnotationResponse,
  SyncResult,
  CreateDatasetBody,
  DashboardResponse,
  ExtractFeaturesResponse,
  SimilarityResponse,
  SelectionMetricsResponse,
  UncoveredHintsResponse,
  DatasetExport,
  PersistExportResponse,
  ExportFormatItem,
  BulkCreateSampleItem,
  BulkCreateSampleResponse,
  PaginatedResponse,
} from "./types";

export function listDatasets(): Promise<Dataset[]> {
  return req<Dataset[]>("/datasets");
}

export function createDataset(body: CreateDatasetBody): Promise<Dataset> {
  return req<Dataset>("/datasets", {
    method: "POST",
    body: JSON.stringify({
      name: body.name,
      dataset_type: body.dataset_type,
      task_spec: body.task_spec ?? {
        task_type: "classification",
        label_space: [],
      },
      ...(body.storage_mode ? { storage_mode: body.storage_mode } : {}),
    }),
  });
}

export function deleteDataset(id: string): Promise<void> {
  return req<void>(`/datasets/${id}`, { method: "DELETE" });
}

export function getDataset(id: string): Promise<Dataset> {
  return req<Dataset>(`/datasets/${id}`);
}

export function updateLabelSpace(
  datasetId: string,
  labelSpace: string[],
): Promise<Dataset> {
  return req<Dataset>(`/datasets/${datasetId}/label-space`, {
    method: "PATCH",
    body: JSON.stringify({ label_space: labelSpace }),
  });
}

export function getAnnotationStats(
  datasetId: string,
): Promise<DatasetAnnotationStats> {
  return req<DatasetAnnotationStats>(
    `/datasets/${datasetId}/annotation-stats`,
  );
}

export function getSparseSummary(
  datasetId: string,
): Promise<SparseSummaryResponse> {
  return req<SparseSummaryResponse>(
    `/datasets/${datasetId}/sparse-summary`,
  );
}

export function toggleDatasetPublic(
  id: string,
  isPublic: boolean,
): Promise<Dataset> {
  return req<Dataset>(`/datasets/${id}/public`, {
    method: "PATCH",
    body: JSON.stringify({ is_public: isPublic }),
  });
}

export function syncAnnotationsToLs(datasetId: string): Promise<SyncResult> {
  return req<SyncResult>(`/datasets/${datasetId}/sync-annotations-to-ls`, {
    method: "POST",
  });
}

export function bulkCreateAnnotations(
  datasetId: string,
  body: BulkAnnotationRequest,
): Promise<BulkAnnotationResponse> {
  return req<BulkAnnotationResponse>(
    `/datasets/${datasetId}/annotations/bulk`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export function listExportFormats(): Promise<ExportFormatItem[]> {
  return req<ExportFormatItem[]>("/export-formats");
}

export function getExport(datasetId: string): Promise<DatasetExport> {
  return req<DatasetExport>(`/exports/${datasetId}`);
}

export function persistExport(
  datasetId: string,
): Promise<PersistExportResponse> {
  return req<PersistExportResponse>(`/exports/${datasetId}/persist`, {
    method: "POST",
  });
}

export function importViaCube(
  cubeId: string,
  body: {
    dataset_id: string;
    items: BulkCreateSampleItem[];
  },
): Promise<BulkCreateSampleResponse> {
  return req<BulkCreateSampleResponse>(
    `/plugins/${cubeId}/import`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
    120_000,
  );
}

export function exportViaCube(
  cubeId: string,
  body: {
    dataset_id: string;
    [key: string]: unknown;
  },
): Promise<Record<string, unknown>> {
  return req<Record<string, unknown>>(`/plugins/${cubeId}/export`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function extractFeatures(
  datasetId: string,
  force?: boolean,
): Promise<ExtractFeaturesResponse> {
  const qs = force ? "?force=true" : "";
  return req<ExtractFeaturesResponse>(
    `/datasets/${datasetId}/features/extract${qs}`,
    { method: "POST" },
  );
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

export function getSelectionMetrics(
  datasetId: string,
): Promise<SelectionMetricsResponse> {
  return req<SelectionMetricsResponse>(
    `/datasets/${datasetId}/selection-metrics`,
  );
}

export function getUncoveredHints(
  datasetId: string,
): Promise<UncoveredHintsResponse> {
  return req<UncoveredHintsResponse>(
    `/datasets/${datasetId}/hints/uncovered`,
  );
}

export function getEmbedConfig(
  datasetId: string,
): Promise<Record<string, unknown>> {
  return req<Record<string, unknown>>(
    `/datasets/${datasetId}/embed-config`,
  );
}

export function updateEmbedConfig(
  datasetId: string,
  config: { model: string; dimension: number },
): Promise<Record<string, unknown>> {
  return req<Record<string, unknown>>(
    `/datasets/${datasetId}/embed-config`,
    {
      method: "PATCH",
      body: JSON.stringify(config),
    },
  );
}

export function getDashboard(): Promise<DashboardResponse> {
  return req<DashboardResponse>("/dashboard");
}

export function queryDatasetData<T = Record<string, unknown>>(
  datasetId: string,
  queryType: string,
  params: Record<string, unknown> = {},
): Promise<T> {
  return req<T>(`/datasets/${datasetId}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query_type: queryType, params }),
  });
}

export function queryWaferPoints(
  datasetId: string,
): Promise<import("./types").WaferPointsQueryResponse> {
  return queryDatasetData<import("./types").WaferPointsQueryResponse>(
    datasetId,
    "wafer-points",
  );
}

export async function fetchSampleSlice(
  datasetId: string,
  options: import("./types").FetchSampleSliceOptions = {},
): Promise<PaginatedResponse<import("./types").SampleWithLabels>> {
  const params: Record<string, unknown> = {};
  if (options.offset !== undefined) params.offset = options.offset;
  if (options.limit !== undefined) params.limit = options.limit;
  if (options.label !== undefined && options.label !== null)
    params.label = options.label;
  if (options.orderBy !== undefined) params.order_by = options.orderBy;
  if (options.sampleIds !== undefined && options.sampleIds !== null) {
    params.sample_ids = options.sampleIds;
  }

  const response = await queryDatasetData<{
    items: import("./types").SampleWithLabels[];
    total: number;
    error?: string;
  }>(datasetId, "sample-slice", params);

  if (
    response &&
    typeof response === "object" &&
    "error" in response &&
    response.error
  ) {
    const { ApiError } = await import("./client");
    throw new ApiError(String(response.error), 400);
  }

  return { items: response.items ?? [], total: response.total ?? 0 };
}

export { getApiBase };

export type { SimilarityResponse } from "./types";
