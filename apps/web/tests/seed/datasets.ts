/**
 * Dataset seed helpers — create, add samples, delete using orval-generated API functions.
 */
import type {
  CreateDatasetRequest,
  Dataset,
  BulkCreateSampleRequest,
  BulkCreateSampleResponse,
} from '../../src/generated/orval/models';
import {
  createDatasetApiV1DatasetsPost,
  deleteDatasetApiV1DatasetsDatasetIdDelete,
  importSamplesApiV1DatasetsDatasetIdSamplesImportPost,
} from '../../src/generated/orval/endpoints/api';

/**
 * Create a new dataset.
 *
 * IMPORTANT: call {@link getSeedClient} (from `./client`) with a valid
 * token BEFORE calling this.
 */
export async function createDataset(req: CreateDatasetRequest): Promise<Dataset> {
  const res = await createDatasetApiV1DatasetsPost(req);
  return res.data as Dataset;
}

/**
 * Bulk-add samples to an existing dataset.
 */
export async function addSamples(
  datasetId: string,
  req: BulkCreateSampleRequest,
): Promise<BulkCreateSampleResponse> {
  const res = await importSamplesApiV1DatasetsDatasetIdSamplesImportPost(datasetId, req);
  return res.data as BulkCreateSampleResponse;
}

/**
 * Delete a dataset by ID.
 */
export async function deleteDataset(datasetId: string): Promise<void> {
  await deleteDatasetApiV1DatasetsDatasetIdDelete(datasetId);
}
