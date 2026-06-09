import {
  listSamplesApiV1DatasetsDatasetIdSamplesGet,
  createSampleApiV1DatasetsDatasetIdSamplesPost,
  importSamplesApiV1DatasetsDatasetIdSamplesImportPost,
  getSampleApiV1DatasetsDatasetIdSamplesSampleIdGet,
  uploadSampleImageApiV1DatasetsDatasetIdSamplesSampleIdUploadPost,
  listAnnotationsForSampleApiV1DatasetsDatasetIdSamplesSampleIdAnnotationsGet,
  listSamplesWithLabelsEndpointApiV1DatasetsDatasetIdSamplesWithLabelsGet,
} from "@/generated/orval/endpoints/api";
import type {
  BodyUploadSampleImageApiV1DatasetsDatasetIdSamplesSampleIdUploadPost,
  BulkCreateSampleItem,
  BulkCreateSampleResponse,
} from "@/generated/orval/models";
import type {
  Annotation,
  Sample,
  SampleWithLabels,
} from "@/generated/orval/models";
import type {
  PaginatedResponse,
  UploadResponse,
  CreateSampleBody,
} from "./types";

export async function listSamples(
  datasetId: string,
  offset?: number,
  limit?: number,
): Promise<PaginatedResponse<Sample>> {
  return (
    await listSamplesApiV1DatasetsDatasetIdSamplesGet(datasetId, {
      offset,
      limit,
    })
  ).data as PaginatedResponse<Sample>;
}

export async function createSample(
  datasetId: string,
  body: CreateSampleBody,
): Promise<Sample> {
  return (
    await createSampleApiV1DatasetsDatasetIdSamplesPost(datasetId, {
      image_uris: body.image_uris,
      metadata: body.metadata ?? {},
    } as import("@/generated/orval/models/createSampleRequest").CreateSampleRequest)
  ).data as Sample;
}

export async function importSamples(
  datasetId: string,
  items: BulkCreateSampleItem[],
): Promise<BulkCreateSampleResponse> {
  return (
    await importSamplesApiV1DatasetsDatasetIdSamplesImportPost(datasetId, {
      items,
    } as import("@/generated/orval/models/bulkCreateSampleRequest").BulkCreateSampleRequest)
  ).data as BulkCreateSampleResponse;
}

export async function getSample(sampleId: string, datasetId: string): Promise<Sample> {
  return (
    await getSampleApiV1DatasetsDatasetIdSamplesSampleIdGet(datasetId, sampleId)
  ).data as Sample;
}

export async function uploadSampleImage(
  sampleId: string,
  file: File,
  datasetId: string,
): Promise<UploadResponse> {
  const body: BodyUploadSampleImageApiV1DatasetsDatasetIdSamplesSampleIdUploadPost = {
    file,
  };
  return (
    await uploadSampleImageApiV1DatasetsDatasetIdSamplesSampleIdUploadPost(
      datasetId,
      sampleId,
      body,
    )
  ).data as UploadResponse;
}

export async function listAnnotationsForSample(
  sampleId: string,
  datasetId: string,
): Promise<Annotation[]> {
  return (
    await listAnnotationsForSampleApiV1DatasetsDatasetIdSamplesSampleIdAnnotationsGet(
      datasetId,
      sampleId,
    )
  ).data as Annotation[];
}

export async function listSamplesWithLabels(
  datasetId: string,
  offset = 0,
  limit = 50,
  label?: string,
  orderBy = "id",
  withPredictions = false,
): Promise<PaginatedResponse<SampleWithLabels>> {
  return (
    await listSamplesWithLabelsEndpointApiV1DatasetsDatasetIdSamplesWithLabelsGet(
      datasetId,
      {
        offset,
        limit,
        label: label ?? undefined,
        order_by: orderBy,
        with_predictions: withPredictions || undefined,
      },
    )
  ).data as PaginatedResponse<SampleWithLabels>;
}
