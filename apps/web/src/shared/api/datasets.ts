import {
  listDatasetsApiV1DatasetsGet,
  createDatasetApiV1DatasetsPost,
  deleteDatasetApiV1DatasetsDatasetIdDelete,
  getDatasetApiV1DatasetsDatasetIdGet,
  updateLabelSpaceApiV1DatasetsDatasetIdLabelSpacePatch,
  getAnnotationStatsApiV1DatasetsDatasetIdAnnotationStatsGet,
  getSparseSummaryApiV1DatasetsDatasetIdSparseSummaryGet,
  setDatasetPublicApiV1DatasetsDatasetIdPublicPatch,
  syncAnnotationsToLsApiV1DatasetsDatasetIdSyncAnnotationsToLsPost,
  bulkCreateAnnotationsApiV1DatasetsDatasetIdAnnotationsBulkPost,
  listExportFormatsApiV1ExportFormatsGet,
  exportDatasetApiV1ExportsDatasetIdGet,
  exportDatasetPersistApiV1ExportsDatasetIdPersistPost,
  similaritySearchApiV1DatasetsDatasetIdSimilaritySampleIdGet,
  selectionMetricsApiV1DatasetsDatasetIdSelectionMetricsGet,
  uncoveredHintsApiV1DatasetsDatasetIdHintsUncoveredGet,
  getEmbedConfigApiV1DatasetsDatasetIdEmbedConfigGet,
  updateEmbedConfigApiV1DatasetsDatasetIdEmbedConfigPatch,
  getDashboardApiV1DashboardGet,
  queryDatasetDataApiV1DatasetsDatasetIdQueryPost,
  extractFeaturesApiV1DatasetsDatasetIdFeaturesExtractPost,
  listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet,
  updateDatasetApiV1DatasetsDatasetIdPatch,
} from "@/generated/orval/endpoints/api";
import { orvalFetcher } from "@/shared/api/orval-fetcher";
import { getApiBase, withAuthQueryParams } from "./client";
import type {
  DatasetAnnotationStats,
  SparseSummaryResponse,
  BulkAnnotationResponse,
  DashboardResponse,
  SimilarityResponse,
  PersistExportResponse,
  BulkCreateSampleItem,
  BulkCreateSampleResponse,
} from "@/generated/orval/models";
import type { Dataset, SampleWithLabels } from "@/generated/orval/models";
import type {
  SyncResult,
  CreateDatasetBody,
  ExtractFeaturesResponse,
  PaginatedResponse,
} from "./types";
import type {
  SelectionMetricsResponse,
  UncoveredHintsResponse,
  DatasetExport,
  ExportFormatItem,
} from "./ui-helpers";

export async function listDatasets(): Promise<Dataset[]> {
  const pageSize = 200;
  let offset = 0;
  const datasets: Dataset[] = [];

  for (;;) {
    const page = await listDatasetPage({ limit: pageSize, offset });
    datasets.push(...page.items);
    if (datasets.length >= page.total || page.items.length === 0) {
      return datasets;
    }
    offset += page.items.length;
  }
}

export async function listDatasetPage(params: {
  limit: number;
  offset: number;
}): Promise<PaginatedResponse<Dataset>> {
  const res = await listDatasetsApiV1DatasetsGet(params);
  if (res.status !== 200) {
    throw new Error(`Failed to list datasets: ${res.status}`);
  }
  return res.data as PaginatedResponse<Dataset>;
}

export async function createDataset(body: CreateDatasetBody): Promise<Dataset> {
  return (
    await createDatasetApiV1DatasetsPost({
      name: body.name,
      dataset_type:
        body.dataset_type as import("@/generated/orval/models/createDatasetRequestDatasetType").CreateDatasetRequestDatasetType,
      task_spec: body.task_spec ?? {
        task_type: "classification",
        label_space: [],
      },
      ...(body.storage_mode ? { storage_mode: body.storage_mode } : {}),
    })
  ).data as Dataset;
}

export async function deleteDataset(id: string): Promise<void> {
  return (await deleteDatasetApiV1DatasetsDatasetIdDelete(id)).data as void;
}

export async function getDataset(id: string): Promise<Dataset> {
  return (await getDatasetApiV1DatasetsDatasetIdGet(id)).data as Dataset;
}

export async function updateLabelSpace(datasetId: string, labelSpace: string[]): Promise<Dataset> {
  return (
    await updateLabelSpaceApiV1DatasetsDatasetIdLabelSpacePatch(datasetId, {
      label_space: labelSpace,
    })
  ).data as Dataset;
}

export async function getAnnotationStats(datasetId: string): Promise<DatasetAnnotationStats> {
  return (await getAnnotationStatsApiV1DatasetsDatasetIdAnnotationStatsGet(datasetId))
    .data as DatasetAnnotationStats;
}

export async function getSparseSummary(datasetId: string): Promise<SparseSummaryResponse> {
  return (await getSparseSummaryApiV1DatasetsDatasetIdSparseSummaryGet(datasetId))
    .data as SparseSummaryResponse;
}

export async function toggleDatasetPublic(id: string, isPublic: boolean): Promise<Dataset> {
  return (
    await setDatasetPublicApiV1DatasetsDatasetIdPublicPatch(id, {
      is_public: isPublic,
    })
  ).data as Dataset;
}

export async function renameDataset(id: string, name: string): Promise<Dataset> {
  return (
    await updateDatasetApiV1DatasetsDatasetIdPatch(id, {
      name,
    })
  ).data as Dataset;
}

export async function syncAnnotationsToLs(datasetId: string): Promise<SyncResult> {
  return (await syncAnnotationsToLsApiV1DatasetsDatasetIdSyncAnnotationsToLsPost(datasetId))
    .data as SyncResult;
}

export async function bulkCreateAnnotations(
  datasetId: string,
  body: import("@/generated/orval/models").BulkAnnotationRequest,
): Promise<BulkAnnotationResponse> {
  return (
    await bulkCreateAnnotationsApiV1DatasetsDatasetIdAnnotationsBulkPost(
      datasetId,
      body as import("@/generated/orval/models/bulkAnnotationRequest").BulkAnnotationRequest,
    )
  ).data as BulkAnnotationResponse;
}

export async function listExportFormats(): Promise<ExportFormatItem[]> {
  return (await listExportFormatsApiV1ExportFormatsGet()).data as ExportFormatItem[];
}

export async function getExport(datasetId: string): Promise<DatasetExport> {
  return (await exportDatasetApiV1ExportsDatasetIdGet(datasetId)).data as DatasetExport;
}

export async function persistExport(datasetId: string): Promise<PersistExportResponse> {
  return (await exportDatasetPersistApiV1ExportsDatasetIdPersistPost(datasetId))
    .data as PersistExportResponse;
}

export function importViaCube(
  cubeId: string,
  body: {
    dataset_id: string;
    items: BulkCreateSampleItem[];
  },
): Promise<BulkCreateSampleResponse> {
  return orvalFetcher<{
    data: BulkCreateSampleResponse;
    status: number;
    headers: Headers;
  }>(`/api/v1/plugins/${cubeId}/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => r.data);
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
  return orvalFetcher<{
    data: Record<string, unknown>;
    status: number;
    headers: Headers;
  }>(`/api/v1/plugins/${cubeId}/export?dataset_id=${encodeURIComponent(dataset_id)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    ...restProps,
  }).then((r) => r.data);
}

export async function extractFeatures(
  datasetId: string,
  force?: boolean,
): Promise<ExtractFeaturesResponse> {
  return (
    await extractFeaturesApiV1DatasetsDatasetIdFeaturesExtractPost(datasetId, {
      force,
    })
  ).data as ExtractFeaturesResponse;
}

export async function getSimilarity(
  datasetId: string,
  sampleId: string,
  k?: number,
): Promise<SimilarityResponse> {
  return (
    await similaritySearchApiV1DatasetsDatasetIdSimilaritySampleIdGet(
      datasetId,
      sampleId,
      k !== undefined ? { k } : undefined,
    )
  ).data as SimilarityResponse;
}

export async function getSelectionMetrics(datasetId: string): Promise<SelectionMetricsResponse> {
  return (await selectionMetricsApiV1DatasetsDatasetIdSelectionMetricsGet(datasetId))
    .data as SelectionMetricsResponse;
}

export async function getUncoveredHints(datasetId: string): Promise<UncoveredHintsResponse> {
  return (await uncoveredHintsApiV1DatasetsDatasetIdHintsUncoveredGet(datasetId))
    .data as UncoveredHintsResponse;
}

export async function getEmbedConfig(datasetId: string): Promise<Record<string, unknown>> {
  return (await getEmbedConfigApiV1DatasetsDatasetIdEmbedConfigGet(datasetId)).data as Record<
    string,
    unknown
  >;
}

export async function updateEmbedConfig(
  datasetId: string,
  config: { model: string; dimension: number },
): Promise<Record<string, unknown>> {
  return (await updateEmbedConfigApiV1DatasetsDatasetIdEmbedConfigPatch(datasetId, config))
    .data as Record<string, unknown>;
}

export async function getDashboard(): Promise<DashboardResponse> {
  return (await getDashboardApiV1DashboardGet()).data as DashboardResponse;
}

export async function queryDatasetData<T = Record<string, unknown>>(
  datasetId: string,
  queryType: string,
  params: Record<string, unknown> = {},
): Promise<T> {
  return (
    await queryDatasetDataApiV1DatasetsDatasetIdQueryPost(datasetId, {
      query_type: queryType,
      params,
    })
  ).data as T;
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
    throw new ApiError(String(response.error), 400);
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
  return (
    await listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet(
      datasetId,
      viewType,
      offset !== undefined || limit !== undefined ? { offset, limit } : undefined,
    )
  ).data as import("./types").ViewPaginatedResponse<T>;
}

export { getApiBase };

export function buildExportDownloadUrl(uri: string): string {
  return withAuthQueryParams(`/api/v1/download?uri=${encodeURIComponent(uri)}`);
}
