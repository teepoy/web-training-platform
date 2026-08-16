import {
  createPredictionBatchApiV1DatasetCollectionsCollectionIdPredictionBatchesPost,
  listPredictionBatchesApiV1DatasetCollectionsCollectionIdPredictionBatchesGet,
  listPredictionCoverageApiV1DatasetCollectionsCollectionIdPredictionCoverageGet,
  retryPredictionBatchApiV1DatasetCollectionsCollectionIdPredictionBatchesBatchIdRetryPost,
  updateDefaultModelApiV1DatasetCollectionsCollectionIdDefaultModelPatch,
} from "@/generated/orval/endpoints/api";
import type {
  CollectionPredictionBatchResponse,
  CollectionPredictionCoverageResponse,
  CreateCollectionPredictionBatchRequest,
  DatasetCollectionResponse,
  UpdateCollectionDefaultModelRequest,
} from "@/generated/orval/models";

export type PredictionCoverageStatus =
  | "current"
  | "model_mismatch"
  | "data_outdated"
  | "not_predicted";

export type CollectionPredictionCoverage = CollectionPredictionCoverageResponse;
export type CollectionPredictionBatch = CollectionPredictionBatchResponse;
export type CollectionWithDefaultModel = DatasetCollectionResponse;

export function updateCollectionDefaultModel(
  collectionId: string,
  payload: UpdateCollectionDefaultModelRequest,
): Promise<CollectionWithDefaultModel> {
  return updateDefaultModelApiV1DatasetCollectionsCollectionIdDefaultModelPatch(
    collectionId,
    payload,
  );
}

export function listCollectionPredictionCoverage(
  collectionId: string,
  snapshotId: string,
): Promise<CollectionPredictionCoverage[]> {
  return listPredictionCoverageApiV1DatasetCollectionsCollectionIdPredictionCoverageGet(
    collectionId,
    { snapshot_id: snapshotId },
  );
}

export function createCollectionPredictionBatch(
  collectionId: string,
  payload: CreateCollectionPredictionBatchRequest,
): Promise<CollectionPredictionBatch> {
  return createPredictionBatchApiV1DatasetCollectionsCollectionIdPredictionBatchesPost(
    collectionId,
    payload,
  );
}

export function listCollectionPredictionBatches(
  collectionId: string,
): Promise<CollectionPredictionBatch[]> {
  return listPredictionBatchesApiV1DatasetCollectionsCollectionIdPredictionBatchesGet(collectionId);
}

export function retryCollectionPredictionBatch(
  collectionId: string,
  batchId: string,
): Promise<CollectionPredictionBatch> {
  return retryPredictionBatchApiV1DatasetCollectionsCollectionIdPredictionBatchesBatchIdRetryPost(
    collectionId,
    batchId,
  );
}
