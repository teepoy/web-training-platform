/**
 * SC seed helpers — import, annotate, sample listing for live-mode tests.
 *
 * IMPORTANT: call {@link getSeedClient} (from `./client`) with a valid
 * token BEFORE calling any of these functions.
 */
import type {
  ScImportRequest,
  ScImportResponse,
  ScBulkAnnotationRequest,
  ScAnnotationItem,
  Dataset,
} from "../../src/generated/orval/models";
import {
  startScImportApiV1ScImportPost,
  scBulkCreateAnnotationsApiV1DatasetsDatasetIdAnnotationsBulkScPost,
  listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet,
  listDatasetsApiV1DatasetsGet,
} from "../../src/generated/orval/endpoints/api";

/**
 * Start an SC dataset import via the API.
 *
 * Returns the import response which includes `flow_run_id` and status.
 * The import runs asynchronously; use {@link waitForScImportByDatasetName}
 * to wait for the dataset to appear and get its ID.
 */
export async function startScImport(req: ScImportRequest): Promise<ScImportResponse> {
  return startScImportApiV1ScImportPost(req);
}

/**
 * Poll the dataset list until a dataset with the given name appears,
 * returning its ID. Throws after `timeoutMs`.
 */
export async function waitForScImportByDatasetName(
  datasetName: string,
  timeoutMs = 180_000,
): Promise<string> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const page = await listDatasetsApiV1DatasetsGet();
    const datasets: Dataset[] = page.items;
    const found = datasets.find((d) => d.name === datasetName);
    if (found?.id) return found.id;
    await new Promise((r) => setTimeout(r, 3000));
  }
  throw new Error(`SC import for "${datasetName}" did not complete within ${timeoutMs}ms`);
}

/**
 * Bulk-create annotations for SC dataset samples.
 */
export async function scBulkAnnotate(
  datasetId: string,
  annotations: ScAnnotationItem[],
): Promise<{ created: number }> {
  const req: ScBulkAnnotationRequest = { annotations };
  return scBulkCreateAnnotationsApiV1DatasetsDatasetIdAnnotationsBulkScPost(datasetId, req);
}

/** Shape of a single sample item from the patch_image_v1 view. */
export interface ScSampleItem {
  defect_id: string;
  sample_id: string;
}

interface ScSampleListBody {
  items?: ScSampleItem[];
  total?: number;
}

/**
 * List all samples from an SC dataset via the patch_image_v1 view.
 *
 * Paginates automatically through all items.
 */
export async function listScSamples(datasetId: string): Promise<ScSampleItem[]> {
  const allItems: ScSampleItem[] = [];
  let offset = 0;
  const limit = 200;

  while (true) {
    const body: ScSampleListBody =
      await listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet(
        datasetId,
        "patch_image_v1",
        { offset, limit },
      );
    const items = body.items ?? [];
    if (items.length === 0) break;
    allItems.push(...items);
    offset += limit;
    if (offset >= (body.total ?? 0)) break;
  }

  return allItems;
}

/**
 * Import an SC dataset and annotate it with random labels — combined helper
 * for Phase 3 and Phase 4 seed setup.
 *
 * @param inspectionTime  ISO inspection time string
 * @param waferKey        Wafer key number
 * @param annotateCount   Number of samples to annotate
 * @param labels          Label space to randomly assign
 * @returns The dataset ID and count of annotated samples
 */
export async function setupScImportedAndAnnotated(
  inspectionTime: string,
  waferKey: number,
  annotateCount: number,
  labels: string[],
): Promise<{ datasetId: string; annotated: number }> {
  const datasetName = `wafer-seed-${Date.now()}`;
  const importReq: ScImportRequest = {
    source_inspection_time: inspectionTime,
    source_wafer_key: waferKey,
    dataset_name: datasetName,
    storage_mode: "file_shard_sparse",
  };

  await startScImport(importReq);
  const datasetId = await waitForScImportByDatasetName(datasetName);

  const samples = await listScSamples(datasetId);
  const toAnnotate = Math.min(annotateCount, samples.length);
  const shuffled = [...samples].sort(() => Math.random() - 0.5);
  const annotations: ScAnnotationItem[] = shuffled.slice(0, toAnnotate).map((item) => ({
    defect_id: item.defect_id,
    label: labels[Math.floor(Math.random() * labels.length)],
  }));

  const result = await scBulkAnnotate(datasetId, annotations);
  return { datasetId, annotated: result.created ?? annotations.length };
}
