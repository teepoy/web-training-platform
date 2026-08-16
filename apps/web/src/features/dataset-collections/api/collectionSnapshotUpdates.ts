import {
  getSnapshotUpdateStatusApiV1DatasetCollectionsCollectionIdSnapshotUpdateStatusGet,
  refreshSnapshotApiV1DatasetCollectionsCollectionIdRefreshSnapshotPost,
} from "@/generated/orval/endpoints/api";
import type {
  CollectionSnapshotRefreshResponse,
  CollectionSnapshotUpdateStatusResponse,
  CreateDatasetCollectionRevisionRequest,
} from "@/generated/orval/models";

export type CollectionSnapshotUpdateStatus = CollectionSnapshotUpdateStatusResponse;
export type CollectionSnapshotRefreshResult = CollectionSnapshotRefreshResponse;

export function getCollectionSnapshotUpdateStatus(
  collectionId: string,
): Promise<CollectionSnapshotUpdateStatus> {
  return getSnapshotUpdateStatusApiV1DatasetCollectionsCollectionIdSnapshotUpdateStatusGet(
    collectionId,
  );
}

export function refreshCollectionSnapshot(
  collectionId: string,
  payload: CreateDatasetCollectionRevisionRequest,
): Promise<CollectionSnapshotRefreshResult> {
  return refreshSnapshotApiV1DatasetCollectionsCollectionIdRefreshSnapshotPost(
    collectionId,
    payload,
  );
}
