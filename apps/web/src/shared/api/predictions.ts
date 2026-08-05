import {
  listPredictionJobsApiV1PredictionJobsGet,
  listPredictionJobEventsApiV1PredictionJobsJobIdEventsGet,
  listPredictionCollectionsApiV1PredictionCollectionsGet,
  listReviewActionsApiV1PredictionReviewsGet,
  listAnnotationVersionsApiV1PredictionReviewsActionIdAnnotationVersionsGet,
  exportReviewVersionApiV1PredictionReviewsActionIdExportGet,
  persistReviewExportApiV1PredictionReviewsActionIdExportPersistPost,
} from "@/generated/orval/endpoints/api";
import type {
  PredictionJobResponse as PredictionJob,
  PredictionEventResponse as PredictionEvent,
  ReviewActionResponse as ReviewAction,
  AnnotationVersionResponse as AnnotationVersion,
  PredictionCollectionResponse as PredictionCollection,
} from "@/generated/orval/models";
import type { VersionExportResponse } from "./types";

async function collectAll<T>(
  fetchPage: (offset: number, limit: number) => Promise<{ items: T[]; total: number }>,
): Promise<T[]> {
  const items: T[] = [];
  const pageSize = 200;
  while (true) {
    const page = await fetchPage(items.length, pageSize);
    items.push(...page.items);
    if (items.length >= page.total) {
      return items;
    }
    if (page.items.length === 0) {
      throw new Error("Paginated API returned an incomplete empty page");
    }
  }
}

export async function listPredictionJobs(
  datasetId?: string | null,
  collectionId?: string | null,
): Promise<PredictionJob[]> {
  const jobs: PredictionJob[] = [];
  const pageSize = 200;
  let offset = 0;

  while (true) {
    const response = await listPredictionJobsApiV1PredictionJobsGet({
      dataset_id: datasetId ?? undefined,
      collection_id: collectionId ?? undefined,
      offset,
      limit: pageSize,
    });
    jobs.push(...response.items);
    if (jobs.length >= response.total || response.items.length === 0) {
      return jobs;
    }
    offset += response.items.length;
  }
}

export async function listPredictionJobEvents(id: string): Promise<PredictionEvent[]> {
  return collectAll(async (offset, limit) => {
    const response = await listPredictionJobEventsApiV1PredictionJobsJobIdEventsGet(id, {
      offset,
      limit,
    });
    return response;
  });
}

export async function listPredictionCollections(
  datasetId: string,
): Promise<PredictionCollection[]> {
  return collectAll(async (offset, limit) => {
    const response = await listPredictionCollectionsApiV1PredictionCollectionsGet({
      dataset_id: datasetId,
      offset,
      limit,
    });
    return response;
  });
}

export async function listReviewActions(datasetId: string): Promise<ReviewAction[]> {
  return collectAll(async (offset, limit) => {
    const response = await listReviewActionsApiV1PredictionReviewsGet({
      dataset_id: datasetId,
      offset,
      limit,
    });
    return response;
  });
}

export async function listAnnotationVersions(actionId: string): Promise<AnnotationVersion[]> {
  return collectAll(async (offset, limit) => {
    const response =
      await listAnnotationVersionsApiV1PredictionReviewsActionIdAnnotationVersionsGet(actionId, {
        offset,
        limit,
      });
    return response;
  });
}

export async function previewReviewExport(
  actionId: string,
  formatId?: string,
): Promise<Record<string, unknown>> {
  return (await exportReviewVersionApiV1PredictionReviewsActionIdExportGet(actionId, {
    format_id: formatId ?? undefined,
  })) as Record<string, unknown>;
}

export async function persistReviewExport(
  actionId: string,
  formatId?: string,
): Promise<VersionExportResponse> {
  return (await persistReviewExportApiV1PredictionReviewsActionIdExportPersistPost(actionId, {
    format_id: formatId ?? "annotation-version-full-context-v1",
  } as import("@/generated/orval/models/versionExportRequest").VersionExportRequest)) as VersionExportResponse;
}
