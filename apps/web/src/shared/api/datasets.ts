import {
  listDatasetsApiV1DatasetsGet,
  syncAnnotationsToLsApiV1DatasetsDatasetIdSyncAnnotationsToLsPost,
  exportDatasetApiV1ExportsDatasetIdGet,
  queryDatasetDataApiV1DatasetsDatasetIdQueryPost,
  listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet,
} from "@/generated/orval/endpoints/api";
import { orvalFetcher } from "@/shared/api/orval-fetcher";
import { getApiBase, withAuthQueryParams } from "./client";
import type { BulkCreateSampleItem, BulkCreateSampleResponse } from "@/generated/orval/models";
import type { Dataset, SampleWithLabels } from "@/generated/orval/models";
import type { SyncResult, PaginatedResponse } from "./types";
import type { DatasetExport } from "./ui-helpers";

export async function listDatasets(): Promise<Dataset[]> {
  const pageSize = 200;
  let offset = 0;
  const datasets: Dataset[] = [];

  for (;;) {
    const page = await listDatasetsApiV1DatasetsGet({ limit: pageSize, offset });
    datasets.push(...page.items);
    if (datasets.length >= page.total || page.items.length === 0) {
      return datasets;
    }
    offset += page.items.length;
  }
}

export async function syncAnnotationsToLs(datasetId: string): Promise<SyncResult> {
  const result = await syncAnnotationsToLsApiV1DatasetsDatasetIdSyncAnnotationsToLsPost(datasetId);
  return {
    synced_count: result.synced_count,
    errors: result.errors ?? [],
  };
}

export async function getExport(datasetId: string): Promise<DatasetExport> {
  const result = await exportDatasetApiV1ExportsDatasetIdGet(datasetId);
  if (!isDatasetExport(result)) {
    throw new TypeError("Dataset export response has an invalid shape");
  }
  return result;
}

function isDatasetExport(value: unknown): value is DatasetExport {
  return (
    typeof value === "object" &&
    value !== null &&
    "dataset" in value &&
    typeof value.dataset === "object" &&
    value.dataset !== null &&
    "samples" in value &&
    Array.isArray(value.samples) &&
    "annotations" in value &&
    Array.isArray(value.annotations)
  );
}

export function importViaCube(
  cubeId: string,
  body: {
    dataset_id: string;
    items: BulkCreateSampleItem[];
  },
): Promise<BulkCreateSampleResponse> {
  return orvalFetcher<BulkCreateSampleResponse>(`/api/v1/plugins/${cubeId}/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function exportViaCube(
  cubeId: string,
  body: {
    dataset_id: string;
    [key: string]: unknown;
  },
): Promise<Record<string, unknown>> {
  const { dataset_id, ...restBody } = body;
  const restProps = Object.keys(restBody).length > 0 ? { body: JSON.stringify(restBody) } : {};
  return orvalFetcher<Record<string, unknown>>(
    `/api/v1/plugins/${cubeId}/export?dataset_id=${encodeURIComponent(dataset_id)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      ...restProps,
    },
  );
}

export async function queryDatasetData<T = Record<string, unknown>>(
  datasetId: string,
  queryType: string,
  params: Record<string, unknown> = {},
): Promise<T> {
  return (await queryDatasetDataApiV1DatasetsDatasetIdQueryPost(datasetId, {
    query_type: queryType,
    params,
  })) as T;
}

export async function queryWaferPoints(
  datasetId: string,
): Promise<import("./types").WaferPointsQueryResponse> {
  return queryDatasetData<import("./types").WaferPointsQueryResponse>(datasetId, "wafer-points");
}

export async function fetchSampleSlice(
  datasetId: string,
  options: import("./ui-helpers").FetchSampleSliceOptions = {},
): Promise<PaginatedResponse<SampleWithLabels>> {
  const params: Record<string, unknown> = {};
  if (options.offset !== undefined) params.offset = options.offset;
  if (options.limit !== undefined) params.limit = options.limit;
  if (options.label !== undefined && options.label !== null) params.label = options.label;
  if (options.orderBy !== undefined) params.order_by = options.orderBy;
  if (options.sampleIds !== undefined && options.sampleIds !== null) {
    params.sample_ids = options.sampleIds;
  }

  const response = await queryDatasetData<{
    items: SampleWithLabels[];
    total: number;
    error?: string;
  }>(datasetId, "sample-slice", params);

  if (response && typeof response === "object" && "error" in response && response.error) {
    const { ApiError } = await import("./client");
    throw new ApiError({
      kind: "http",
      detail: String(response.error),
      status: 400,
      body: response,
    });
  }

  return { items: response.items ?? [], total: response.total ?? 0 };
}

export async function getViewSamples<
  T extends import("./types").ViewRowV1 = import("./types").ViewRowV1,
>(
  datasetId: string,
  viewType: string,
  offset?: number,
  limit?: number,
): Promise<import("./types").ViewPaginatedResponse<T>> {
  return (await listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet(
    datasetId,
    viewType,
    offset !== undefined || limit !== undefined ? { offset, limit } : undefined,
  )) as import("./types").ViewPaginatedResponse<T>;
}

export { getApiBase };

export function buildExportDownloadUrl(uri: string): string {
  return withAuthQueryParams(`/api/v1/download?uri=${encodeURIComponent(uri)}`);
}
