import {
  runPredictionsApiV1PredictionsRunPost,
  listPredictionJobsApiV1PredictionJobsGet,
  getPredictionJobApiV1PredictionJobsJobIdGet,
  listPredictionJobPredictionsApiV1PredictionJobsJobIdPredictionsGet,
  listPredictionJobEventsApiV1PredictionJobsJobIdEventsGet,
  cancelPredictionJobApiV1PredictionJobsJobIdCancelPost,
  predictSingleApiV1PredictionsSinglePost,
  listSamplePredictionsApiV1SamplesSampleIdPredictionsGet,
  createPredictionCollectionApiV1PredictionCollectionsPost,
  listPredictionCollectionsApiV1PredictionCollectionsGet,
  syncPredictionCollectionToLabelStudioApiV1PredictionCollectionsCollectionIdSyncLabelStudioPost,
  createReviewActionApiV1PredictionReviewsPost,
  listReviewActionsApiV1PredictionReviewsGet,
  getReviewActionApiV1PredictionReviewsActionIdGet,
  deleteReviewActionApiV1PredictionReviewsActionIdDelete,
  saveReviewAnnotationsApiV1PredictionReviewsActionIdAnnotationsPost,
  listAnnotationVersionsApiV1PredictionReviewsActionIdAnnotationVersionsGet,
  exportReviewVersionApiV1PredictionReviewsActionIdExportGet,
  persistReviewExportApiV1PredictionReviewsActionIdExportPersistPost,
  createTrainAndPredictJobApiV1TrainingJobsTrainAndPredictPost,
} from "@/generated/orval/endpoints/api";
import type {
  RunPredictionRequest,
  PredictSingleRequest,
  SaveReviewAnnotationItem,
  SaveReviewAnnotationsResponse,
  TrainAndPredictRequest,
  TrainAndPredictResponse,
} from "@/generated/orval/models";
import type { PredictionJobResponse as PredictionJob, PredictionResultResponse as PredictionResult, PredictionEventResponse as PredictionEvent, ReviewActionResponse as ReviewAction, AnnotationVersionResponse as AnnotationVersion, PredictionCollectionResponse as PredictionCollection, SyncPredictionCollectionResponse } from "@/generated/orval/models";
import type { CreatePredictionCollectionRequest, VersionExportResponse } from "./types";

export async function runPredictions(
  request: RunPredictionRequest,
): Promise<PredictionJob> {
  return (await
    runPredictionsApiV1PredictionsRunPost(
      request as import("@/generated/orval/models/runPredictionRequest").RunPredictionRequest,
    )).data as PredictionJob;
}

export async function startTrainAndPredict(
  request: TrainAndPredictRequest,
): Promise<TrainAndPredictResponse> {
  return (
    await createTrainAndPredictJobApiV1TrainingJobsTrainAndPredictPost(request)
  ).data as TrainAndPredictResponse;
}

export async function listPredictionJobs(
  datasetId?: string | null,
): Promise<PredictionJob[]> {
  return (await listPredictionJobsApiV1PredictionJobsGet(
    datasetId ? { dataset_id: datasetId } : undefined,
  )).data as PredictionJob[];
}

export async function getPredictionJob(id: string): Promise<PredictionJob> {
  return (await getPredictionJobApiV1PredictionJobsJobIdGet(id)).data as PredictionJob;
}

export async function listPredictionJobPredictions(
  id: string,
): Promise<PredictionResult[]> {
  return (await
    listPredictionJobPredictionsApiV1PredictionJobsJobIdPredictionsGet(id)).data as PredictionResult[];
}

export async function listPredictionJobEvents(
  id: string,
): Promise<PredictionEvent[]> {
  return (await
    listPredictionJobEventsApiV1PredictionJobsJobIdEventsGet(id)).data as PredictionEvent[];
}

export async function cancelPredictionJob(
  id: string,
): Promise<{ cancelled: boolean }> {
  return (await
    cancelPredictionJobApiV1PredictionJobsJobIdCancelPost(id)).data as { cancelled: boolean };
}

export async function predictSingle(
  request: PredictSingleRequest,
): Promise<PredictionResult> {
  return (await
    predictSingleApiV1PredictionsSinglePost(
      request as import("@/generated/orval/models/predictSingleRequest").PredictSingleRequest,
    )).data as PredictionResult;
}

export async function listSamplePredictions(
  sampleId: string,
  modelVersion?: string | null,
): Promise<PredictionResult[]> {
  return (await
    listSamplePredictionsApiV1SamplesSampleIdPredictionsGet(sampleId, {
      model_version: modelVersion ?? undefined,
    })).data as PredictionResult[];
}

export async function createPredictionCollection(
  request: CreatePredictionCollectionRequest,
): Promise<PredictionCollection> {
  return (await
    createPredictionCollectionApiV1PredictionCollectionsPost(
      request as import("@/generated/orval/models/predictionCollectionRequest").PredictionCollectionRequest,
    )).data as PredictionCollection;
}

export async function listPredictionCollections(
  datasetId: string,
): Promise<PredictionCollection[]> {
  return (await
    listPredictionCollectionsApiV1PredictionCollectionsGet({
      dataset_id: datasetId,
    })).data as PredictionCollection[];
}

export async function syncPredictionCollection(
  collectionId: string,
  syncTag?: string | null,
): Promise<SyncPredictionCollectionResponse> {
  return (await
    syncPredictionCollectionToLabelStudioApiV1PredictionCollectionsCollectionIdSyncLabelStudioPost(
      collectionId,
      {
        sync_tag: syncTag ?? undefined,
      } as import("@/generated/orval/models/syncPredictionCollectionRequest").SyncPredictionCollectionRequest,
    )).data as SyncPredictionCollectionResponse;
}

export async function createReviewAction(params: {
  dataset_id: string;
  model_id: string;
  model_version?: string | null;
  collection_id?: string | null;
  sync_tag?: string | null;
}): Promise<ReviewAction> {
  return (await
    createReviewActionApiV1PredictionReviewsPost(
      params as import("@/generated/orval/models/createReviewActionRequest").CreateReviewActionRequest,
    )).data as ReviewAction;
}

export async function listReviewActions(datasetId: string): Promise<ReviewAction[]> {
  return (await
    listReviewActionsApiV1PredictionReviewsGet({
      dataset_id: datasetId,
    })).data as ReviewAction[];
}

export async function getReviewAction(actionId: string): Promise<ReviewAction> {
  return (await
    getReviewActionApiV1PredictionReviewsActionIdGet(actionId)).data as ReviewAction;
}

export async function deleteReviewAction(actionId: string): Promise<void> {
  return (await
    deleteReviewActionApiV1PredictionReviewsActionIdDelete(actionId)).data as void;
}

export async function saveReviewAnnotations(
  actionId: string,
  items: SaveReviewAnnotationItem[],
): Promise<SaveReviewAnnotationsResponse> {
  return (await
    saveReviewAnnotationsApiV1PredictionReviewsActionIdAnnotationsPost(
      actionId,
      {
        items,
      } as import("@/generated/orval/models/saveReviewAnnotationsRequest").SaveReviewAnnotationsRequest,
    )).data as SaveReviewAnnotationsResponse;
}

export async function listAnnotationVersions(
  actionId: string,
): Promise<AnnotationVersion[]> {
  return (await
    listAnnotationVersionsApiV1PredictionReviewsActionIdAnnotationVersionsGet(
      actionId,
    )).data as AnnotationVersion[];
}

export async function previewReviewExport(
  actionId: string,
  formatId?: string,
): Promise<Record<string, unknown>> {
  return (await
    exportReviewVersionApiV1PredictionReviewsActionIdExportGet(actionId, {
      format_id: formatId ?? undefined,
    })).data as Record<string, unknown>;
}

export async function persistReviewExport(
  actionId: string,
  formatId?: string,
): Promise<VersionExportResponse> {
  return (await
    persistReviewExportApiV1PredictionReviewsActionIdExportPersistPost(
      actionId,
      {
        format_id: formatId ?? "annotation-version-full-context-v1",
      } as import("@/generated/orval/models/versionExportRequest").VersionExportRequest,
    )).data as VersionExportResponse;
}
